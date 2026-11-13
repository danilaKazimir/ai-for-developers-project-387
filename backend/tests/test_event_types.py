import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from backend.tests.contract import assert_contract_response

pytestmark = pytest.mark.integration


async def test_created_event_type_is_in_public_catalog(postgres_app: FastAPI) -> None:
    body = {
        "name": "  Знакомство  ",
        "description": "Обсудим задачу",
        "durationMinutes": 45,
    }
    async with AsyncClient(
        transport=ASGITransport(app=postgres_app), base_url="http://test"
    ) as client:
        created = await client.post(
            "/api/organizer/event-types",
            json=body,
        )
        assert created.status_code == 201
        assert created.json() == {**body, "name": "Знакомство", "id": created.json()["id"]}
        from uuid import UUID

        assert UUID(hex=created.json()["id"]).version == 4
        assert len(created.json()["id"]) == 32
        assert_contract_response(created)
        catalog = await client.get("/api/event-types")
        assert catalog.json() == {"items": [created.json()]}
        assert_contract_response(catalog)


@pytest.mark.parametrize(
    "field,value",
    [
        ("name", "   "),
        ("name", "n" * 121),
        ("description", "d" * 2001),
        ("durationMinutes", 0),
        ("durationMinutes", 541),
        ("durationMinutes", 30.5),
        ("durationMinutes", "30"),
        ("durationMinutes", True),
        ("undeclared", "private"),
        ("id", "legacy-link"),
    ],
)
async def test_invalid_event_type_is_not_created(
    postgres_app: FastAPI, field: str, value: object
) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=postgres_app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/organizer/event-types",
            json={
                "name": "Intro",
                "description": "",
                "durationMinutes": 30,
                field: value,
            },
        )
        assert response.status_code == 422
        assert response.json()["code"] == "VALIDATION_ERROR"
        assert_contract_response(response)
        assert (await client.get("/api/event-types")).json() == {"items": []}


@pytest.mark.parametrize("duration", [1, 45, 540])
async def test_event_type_accepts_limits_after_trimming_name(
    postgres_app: FastAPI, duration: int
) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=postgres_app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/organizer/event-types",
            json={
                "name": "  " + "n" * 120 + "  ",
                "description": "d" * 2000,
                "durationMinutes": duration,
            },
        )
        assert response.status_code == 201
        assert response.json()["name"] == "n" * 120
        assert_contract_response(response)


async def test_catalog_survives_application_restart(
    postgres_app: FastAPI, test_database_url: str
) -> None:
    from backend.app.config import Settings
    from backend.app.main import create_app

    async with AsyncClient(
        transport=ASGITransport(app=postgres_app), base_url="http://test"
    ) as client:
        created = await client.post(
            "/api/organizer/event-types",
            json={
                "name": "Сохранённый тип",
                "description": "",
                "durationMinutes": 30,
            },
        )
        assert created.status_code == 201
    restarted = create_app(Settings(database_url=test_database_url))
    async with (
        restarted.router.lifespan_context(restarted),
        AsyncClient(transport=ASGITransport(app=restarted), base_url="http://test") as client,
    ):
        catalog = await client.get("/api/event-types")
        assert catalog.json() == {"items": [created.json()]}
        assert_contract_response(catalog)


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/api/event-types"),
        ("POST", "/api/organizer/event-types"),
        ("GET", "/api/event-types/intro/slots"),
    ],
)
async def test_database_unavailable_has_no_connection_details(
    test_database_url: str, method: str, path: str
) -> None:
    from sqlalchemy.engine import make_url

    from backend.app.config import Settings
    from backend.app.main import create_app

    unavailable = make_url(test_database_url).set(port=1).render_as_string(hide_password=False)
    app = create_app(Settings(database_url=unavailable))
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        response = await client.request(
            method,
            path,
            json={
                "name": "Intro",
                "description": "",
                "durationMinutes": 30,
            }
            if method == "POST"
            else None,
        )
        assert response.status_code == 503
        assert response.json()["code"] == "DATABASE_UNAVAILABLE"
        assert "postgresql" not in response.text
        assert "127.0.0.1" not in response.text
        assert_contract_response(response)


async def test_identical_names_have_distinct_permanent_ids(postgres_app: FastAPI) -> None:
    from uuid import UUID

    async with AsyncClient(
        transport=ASGITransport(app=postgres_app), base_url="http://test"
    ) as client:
        items = []
        for _ in range(2):
            response = await client.post(
                "/api/organizer/event-types",
                json={"name": "Повтор", "description": "", "durationMinutes": 30},
            )
            assert response.status_code == 201
            assert_contract_response(response)
            item = response.json()
            assert UUID(item["id"]).version == 4
            assert UUID(item["id"]).hex == item["id"]
            items.append(item)
        assert items[0]["id"] != items[1]["id"]
        catalog = await client.get("/api/event-types")
        assert catalog.json()["items"] == sorted(items, key=lambda item: item["id"])


@pytest.mark.parametrize("mode", ["recover", "exhausted", "other_integrity"])
async def test_generated_id_collisions(
    postgres_app: FastAPI, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    from types import SimpleNamespace

    body = {"name": "Первый", "description": "", "durationMinutes": 30}
    async with AsyncClient(
        transport=ASGITransport(app=postgres_app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        monkeypatch.setattr("backend.app.event_types.uuid4", lambda: SimpleNamespace(hex="a" * 32))
        first = await client.post("/api/organizer/event-types", json=body)
        assert first.status_code == 201
        values = iter(
            ["a" * 32, "b" * 32]
            if mode == "recover"
            else ["a" * 32] * 3
            if mode == "exhausted"
            else ["invalid--id"]
        )
        attempts: list[int] = []

        def next_id() -> SimpleNamespace:
            attempts.append(1)
            return SimpleNamespace(hex=next(values))

        monkeypatch.setattr("backend.app.event_types.uuid4", next_id)
        response = await client.post("/api/organizer/event-types", json={**body, "name": "Другой"})
        assert len(attempts) == {"recover": 2, "exhausted": 3, "other_integrity": 1}[mode]
        assert response.status_code == (201 if mode == "recover" else 500)
        assert_contract_response(response)
        if mode != "recover":
            assert response.json()["code"] == "INTERNAL_ERROR"
        else:
            assert response.json()["id"] == "b" * 32
        items = (await client.get("/api/event-types")).json()["items"]
        assert len(items) == (2 if mode == "recover" else 1)
        assert items[0] == {**body, "id": "a" * 32}


async def test_legacy_link_and_booking_remain_usable(postgres_app: FastAPI) -> None:
    from datetime import datetime

    from backend.app.models import BookingRecord, EventTypeRecord

    postgres_app.state.clock = lambda: datetime.fromisoformat("2026-11-04T05:00:00+00:00")
    async with postgres_app.state.session_factory() as session:
        session.add(
            EventTypeRecord(
                id="legacy-link", name="Старое событие", description="", duration_minutes=30
            )
        )
        await session.flush()
        session.add(
            BookingRecord(
                event_type_id="legacy-link",
                starts_at=datetime.fromisoformat("2026-11-04T07:00:00+00:00"),
                ends_at=datetime.fromisoformat("2026-11-04T07:30:00+00:00"),
                guest_name="Первый гость",
                guest_email="legacy@example.com",
            )
        )
        await session.commit()
    async with AsyncClient(
        transport=ASGITransport(app=postgres_app), base_url="http://test"
    ) as client:
        slots = await client.get("/api/event-types/legacy-link/slots")
        assert slots.status_code == 200
        assert_contract_response(slots)
        assert slots.json()["eventType"]["id"] == "legacy-link"
        booked = await client.post(
            "/api/bookings",
            json={
                "eventTypeId": "legacy-link",
                "startsAt": "2026-11-04T07:30:00Z",
                "guest": {"name": "Второй", "email": "new@example.com"},
            },
        )
        assert booked.status_code == 201
        assert_contract_response(booked)
        upcoming = await client.get("/api/organizer/bookings")
        assert_contract_response(upcoming)
        assert len(upcoming.json()["items"]) == 2
        assert {item["eventType"]["id"] for item in upcoming.json()["items"]} == {"legacy-link"}
