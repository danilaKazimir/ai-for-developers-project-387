from collections.abc import AsyncIterator
from typing import cast
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel, ValidationError
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.config import Settings
from backend.app.db import get_session
from backend.app.generated.models import ApiError, HealthStatus
from backend.app.main import create_app
from backend.tests.contract import assert_contract_response


@pytest.fixture
def session() -> AsyncMock:
    return AsyncMock(spec=AsyncSession)


@pytest.fixture
async def client(session: AsyncMock) -> AsyncIterator[AsyncClient]:
    app = create_app(
        Settings(database_url="postgresql+psycopg://calendar:calendar@127.0.0.1/calendar")
    )

    async def override_session() -> AsyncIterator[AsyncSession]:
        yield cast(AsyncSession, session)

    app.dependency_overrides[get_session] = override_session
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http,
    ):
        yield http


async def test_health_matches_contract(client: AsyncClient, session: AsyncMock) -> None:
    response = await client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}
    session.execute.assert_awaited_once()
    assert_contract_response(response)


async def test_database_failure_matches_contract_without_leaking_details(
    client: AsyncClient, session: AsyncMock
) -> None:
    session.execute.side_effect = OperationalError(
        "SELECT 1", {}, RuntimeError("postgresql://user:secret-password@private-host/database")
    )
    response = await client.get("/api/health")
    assert response.status_code == 503
    assert response.json() == {
        "code": "DATABASE_UNAVAILABLE",
        "message": "Сервис временно недоступен. Повторите попытку позже",
    }
    assert "secret-password" not in response.text
    assert "private-host" not in response.text
    assert_contract_response(response)


def test_settings_require_psycopg_postgresql() -> None:
    with pytest.raises(ValidationError, match=r"postgresql\+psycopg"):
        Settings(database_url="sqlite+aiosqlite:///:memory:")


@pytest.mark.parametrize(
    ("model", "body"),
    [
        (HealthStatus, {"status": "ok", "database": "ok"}),
        (ApiError, {"code": "DATABASE_UNAVAILABLE", "message": "Unavailable"}),
    ],
)
def test_generated_models_reject_undeclared_fields(
    model: type[BaseModel], body: dict[str, str]
) -> None:
    with pytest.raises(ValidationError, match="extra_forbidden"):
        model.model_validate({**body, "undeclared": "must not be accepted"})
