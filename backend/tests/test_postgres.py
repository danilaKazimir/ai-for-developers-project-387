import asyncio
from typing import cast

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.tests.contract import assert_contract_response

pytestmark = pytest.mark.integration


async def test_real_postgresql_health(postgres_app: FastAPI) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=postgres_app), base_url="http://test"
    ) as client:
        responses = await asyncio.gather(*(client.get("/api/health") for _ in range(3)))
    for response in responses:
        assert response.status_code == 200
        assert_contract_response(response)


async def test_separate_sessions_for_parallel_work(postgres_app: FastAPI) -> None:
    factory = cast(async_sessionmaker[AsyncSession], postgres_app.state.session_factory)
    async with factory() as first, factory() as second:
        assert first is not second
        rows = await asyncio.gather(
            first.scalar(text("SELECT pg_backend_pid()")),
            second.scalar(text("SELECT pg_backend_pid()")),
        )
        assert rows[0] != rows[1]


async def test_migrations_roundtrip(
    test_database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", test_database_url)
    config = Config("alembic.ini")
    await asyncio.to_thread(command.downgrade, config, "base")
    await asyncio.to_thread(command.upgrade, config, "head")
    engine = create_async_engine(test_database_url)
    try:
        async with engine.connect() as connection:
            assert await connection.scalar(text("SELECT version_num FROM alembic_version")) == (
                "0003_bookings"
            )
            assert (
                await connection.scalar(text("SELECT timezone FROM calendars WHERE id = 1"))
                == "Europe/Moscow"
            )
        await asyncio.to_thread(command.check, config)
        await asyncio.to_thread(command.downgrade, config, "0001_baseline")
        async with engine.connect() as connection:
            assert await connection.scalar(text("SELECT to_regclass('event_types')")) is None
            assert await connection.scalar(text("SELECT to_regclass('calendars')")) is None
        await asyncio.to_thread(command.upgrade, config, "head")
    finally:
        await engine.dispose()


@pytest.mark.parametrize(
    "values",
    [
        ("Bad", "Name", "", 30),
        ("a" * 65, "Name", "", 30),
        ("valid", " ", "", 30),
        ("valid", "n" * 121, "", 30),
        ("valid", "Name", "d" * 2001, 30),
        ("valid", "Name", "", 0),
        ("valid", "Name", "", 541),
    ],
)
async def test_migration_enforces_event_type_constraints(
    postgres_app: FastAPI, test_database_url: str, values: tuple[str, str, str, int]
) -> None:
    from sqlalchemy.exc import DataError, IntegrityError

    engine = create_async_engine(test_database_url)
    try:
        with pytest.raises((IntegrityError, DataError)):
            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        "INSERT INTO event_types (id, name, description, duration_minutes) "
                        "VALUES (:id, :name, :description, :duration)"
                    ),
                    dict(zip(["id", "name", "description", "duration"], values, strict=True)),
                )
    finally:
        await engine.dispose()
