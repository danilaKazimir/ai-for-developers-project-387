from datetime import datetime

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from backend.tests.contract import assert_contract_response
from backend.tests.test_bookings import add_type, booking_payload

pytestmark = pytest.mark.integration


async def test_organizer_reads_saved_contacts_across_types_without_a_window_limit(
    postgres_app: FastAPI,
) -> None:
    postgres_app.state.clock = lambda: datetime.fromisoformat("2026-11-04T05:00:00+00:00")
    async with AsyncClient(
        transport=ASGITransport(app=postgres_app), base_url="http://test"
    ) as client:
        empty = await client.get("/api/organizer/bookings")
        assert empty.status_code == 200
        assert empty.json() == {"items": []}
        assert_contract_response(empty)
        long = await add_type(client, "long", 60)
        short = await add_type(client, "short", 30)
        saved = []
        for start, type_id in [
            ("2026-11-04T09:00:00Z", short),
            ("2026-11-04T07:00:00Z", long),
            ("2026-11-04T08:00:00Z", short),
        ]:
            payload = booking_payload(start, type_id)
            payload["guest"] = {
                "name": " Гость ",
                "email": "private@example.com",
                "comment": "Секрет",
            }
            response = await client.post("/api/bookings", json=payload)
            assert response.status_code == 201
            saved.append(response.json())
        # A list has no availability-window bound, even after the clock moves back.
        postgres_app.state.clock = lambda: datetime.fromisoformat("2026-10-01T00:00:00+00:00")
        all_meetings = await client.get("/api/organizer/bookings")
        assert_contract_response(all_meetings)
        assert [item["id"] for item in all_meetings.json()["items"]] == [
            saved[1]["id"],
            saved[2]["id"],
            saved[0]["id"],
        ]
        # Exactly now is upcoming; an ongoing meeting is excluded.
        postgres_app.state.clock = lambda: datetime.fromisoformat("2026-11-04T08:00:00+00:00")
        upcoming = await client.get("/api/organizer/bookings")
        assert_contract_response(upcoming)
        items = upcoming.json()["items"]
        assert [item["id"] for item in items] == [saved[2]["id"], saved[0]["id"]]
        assert items[0] == {
            **saved[2],
            "guest": {"name": "Гость", "email": "private@example.com", "comment": "Секрет"},
        }
        postgres_app.state.clock = lambda: datetime.fromisoformat("2026-11-04T07:30:00+00:00")
        ongoing = await client.get("/api/organizer/bookings")
        assert_contract_response(ongoing)
        assert [item["id"] for item in ongoing.json()["items"]] == [saved[2]["id"], saved[0]["id"]]
        assert upcoming.headers["cache-control"] == "private, no-store"


async def test_organizer_list_database_error_is_private_and_matches_contract(
    test_database_url: str,
) -> None:
    from sqlalchemy.engine import make_url

    from backend.app.config import Settings
    from backend.app.main import create_app

    app = create_app(
        Settings(
            database_url=make_url(test_database_url)
            .set(port=1)
            .render_as_string(hide_password=False),
        )
    )
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        response = await client.get("/api/organizer/bookings")
        assert response.status_code == 503
        assert response.headers["cache-control"] == "private, no-store"
        assert_contract_response(response)
        assert "postgresql" not in response.text


async def test_organizer_unexpected_error_is_private(postgres_app: FastAPI) -> None:
    def unavailable_clock() -> datetime:
        raise RuntimeError("private infrastructure detail")

    postgres_app.state.clock = unavailable_clock
    async with AsyncClient(
        transport=ASGITransport(app=postgres_app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/organizer/bookings")
        assert response.status_code == 500
        assert_contract_response(response)
        assert "private infrastructure detail" not in response.text
        assert response.headers["cache-control"] == "private, no-store"
