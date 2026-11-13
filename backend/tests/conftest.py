import asyncio
import os
from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from backend.app.config import Settings
from backend.app.main import create_app


@pytest.fixture
def test_database_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.fail("TEST_DATABASE_URL is required; see README.md or run mise run test:unit")
    test_url = make_url(url)
    app_url = os.environ.get("DATABASE_URL")
    if not test_url.database or not test_url.database.endswith("_test"):
        pytest.fail("TEST_DATABASE_URL must use a dedicated database ending in _test")
    if app_url and test_url == make_url(app_url):
        pytest.fail("TEST_DATABASE_URL must differ from DATABASE_URL")
    Settings(database_url=url)
    return url


@pytest.fixture
async def postgres_app(
    test_database_url: str, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[FastAPI]:
    monkeypatch.setenv("DATABASE_URL", test_database_url)
    await asyncio.to_thread(command.upgrade, Config("alembic.ini"), "head")
    engine = create_async_engine(test_database_url)
    async with engine.begin() as connection:
        await connection.execute(text("DELETE FROM bookings"))
        await connection.execute(text("DELETE FROM event_types"))
        await connection.execute(
            text("UPDATE calendars SET timezone = 'Europe/Moscow' WHERE id = 1")
        )
    await engine.dispose()
    app = create_app(
        Settings(
            database_url=make_url(test_database_url)
            .update_query_dict({"application_name": f"booking-test-{uuid4()}"})
            .render_as_string(hide_password=False),
        )
    )
    async with app.router.lifespan_context(app):
        try:
            yield app
        finally:
            async with app.state.session_factory() as session:
                await session.execute(
                    text("UPDATE calendars SET timezone = 'Europe/Moscow' WHERE id = 1")
                )
                await session.commit()
