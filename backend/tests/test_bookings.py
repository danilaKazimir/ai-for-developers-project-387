from datetime import datetime
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient, Response
from psycopg import Error

from backend.tests.contract import assert_contract_response
from backend.tests.test_slots import create_type

pytestmark = pytest.mark.integration


async def test_guest_books_and_occupancy_is_shared_without_exposing_contacts(
    postgres_app: FastAPI,
) -> None:
    postgres_app.state.clock = lambda: datetime.fromisoformat("2026-11-04T05:00:00+00:00")
    async with AsyncClient(
        transport=ASGITransport(app=postgres_app), base_url="http://test"
    ) as client:
        intro = await create_type(client, 60)
        response = await client.post(
            "/api/bookings",
            json={
                "eventTypeId": intro,
                "startsAt": "2026-11-04T10:00:00+03:00",
                "guest": {"name": "  Гость  ", "email": "guest@example.com", "comment": "Секрет"},
            },
        )
        assert response.status_code == 201
        assert_contract_response(response)
        result = response.json()
        assert result["startsAt"] == "2026-11-04T07:00:00Z"
        assert result["endsAt"] == "2026-11-04T08:00:00Z"
        assert result["timezone"] == "Europe/Moscow"
        assert result["eventType"]["id"] == intro
        for path in ("/api/event-types", f"/api/event-types/{intro}/slots"):
            public = await client.get(path)
            assert_contract_response(public)
            assert all(
                secret not in public.text
                for secret in ("guest@example.com", "Секрет", result["id"])
            )
        starts = [slot["startsAt"] for slot in public.json()["days"][0]["slots"]]
        assert "2026-11-04T07:00:00Z" not in starts
        assert "2026-11-04T07:30:00Z" not in starts
        assert "2026-11-04T08:00:00Z" in starts


async def add_type(client: AsyncClient, name: str, duration: int) -> str:
    response = await client.post(
        "/api/organizer/event-types",
        json={
            "name": name,
            "description": "",
            "durationMinutes": duration,
        },
    )
    assert response.status_code == 201
    return str(response.json()["id"])


def booking_payload(
    start: str = "2026-11-04T07:00:00Z", event_type: str = "intro"
) -> dict[str, Any]:
    return {
        "eventTypeId": event_type,
        "startsAt": start,
        "guest": {"name": " Гость ", "email": "guest@example.com"},
    }


@pytest.mark.parametrize(
    "start,duration,status",
    [
        ("06:30", 60, 409),
        ("07:00", 30, 409),
        ("07:30", 30, 409),
        ("07:00", 120, 409),
        ("07:30", 60, 409),
        ("06:00", 60, 201),
        ("08:00", 30, 201),
    ],
)
async def test_overlap_and_adjacency_across_types(
    postgres_app: FastAPI, start: str, duration: int, status: int
) -> None:
    postgres_app.state.clock = lambda: datetime.fromisoformat("2026-11-04T05:00:00+00:00")
    async with AsyncClient(
        transport=ASGITransport(app=postgres_app), base_url="http://test"
    ) as client:
        intro = await create_type(client, 60)
        other = await add_type(client, "other", duration)
        assert (
            await client.post("/api/bookings", json=booking_payload(event_type=intro))
        ).status_code == 201
        response = await client.post(
            "/api/bookings", json=booking_payload(f"2026-11-04T{start}:00Z", other)
        )
        assert response.status_code == status
        assert_contract_response(response)
        if status == 409:
            assert response.json()["code"] == "TIME_CONFLICT"
        public = await client.get(f"/api/event-types/{other}/slots")
        assert_contract_response(public)
        assert all(
            slot["startsAt"] != "2026-11-04T07:00:00Z" for slot in public.json()["days"][0]["slots"]
        )


@pytest.mark.parametrize(
    "change,status,code",
    [
        ({"startsAt": "2026-11-04T05:00:00Z"}, 422, "SLOT_NOT_BOOKABLE"),
        ({"startsAt": "2026-11-18T06:00:00Z"}, 422, "SLOT_NOT_BOOKABLE"),
        ({"startsAt": "2026-11-07T06:00:00Z"}, 422, "SLOT_NOT_BOOKABLE"),
        ({"startsAt": "2026-11-04T07:15:00Z"}, 422, "SLOT_NOT_BOOKABLE"),
        ({"startsAt": "2026-11-04T14:30:00Z"}, 422, "SLOT_NOT_BOOKABLE"),
        ({"startsAt": "2026-11-04T07:00:01Z"}, 422, "SLOT_NOT_BOOKABLE"),
        ({"startsAt": "2026-11-04T07:00:00"}, 422, "VALIDATION_ERROR"),
        ({"startsAt": "2026-11-04 07:00:00Z"}, 422, "VALIDATION_ERROR"),
        ({"startsAt": "2026-11-04T07:00Z"}, 422, "VALIDATION_ERROR"),
        ({"startsAt": 1793775600}, 422, "VALIDATION_ERROR"),
        ({"eventTypeId": "missing"}, 404, "EVENT_TYPE_NOT_FOUND"),
        ({"eventTypeId": "Bad"}, 422, "VALIDATION_ERROR"),
        ({"endsAt": "2026-11-04T08:00:00Z"}, 422, "VALIDATION_ERROR"),
        ({"durationMinutes": 30}, 422, "VALIDATION_ERROR"),
        ({"organizerId": "other"}, 422, "VALIDATION_ERROR"),
        ({"guest": {"name": " ", "email": "a@example.com"}}, 422, "VALIDATION_ERROR"),
        ({"guest": {"name": "a" * 121, "email": "a@example.com"}}, 422, "VALIDATION_ERROR"),
        ({"guest": {"name": "Гость", "email": "broken"}}, 422, "VALIDATION_ERROR"),
        (
            {"guest": {"name": "Гость", "email": "a@example.com", "comment": "a" * 2001}},
            422,
            "VALIDATION_ERROR",
        ),
        (
            {"guest": {"name": "Гость", "email": "a@example.com", "comment": None}},
            422,
            "VALIDATION_ERROR",
        ),
        (
            {"guest": {"name": "Гость", "email": "a@example.com", "private": True}},
            422,
            "VALIDATION_ERROR",
        ),
    ],
)
async def test_invalid_booking_never_creates_a_meeting(
    postgres_app: FastAPI, change: dict[str, Any], status: int, code: str
) -> None:
    postgres_app.state.clock = lambda: datetime.fromisoformat("2026-11-04T05:00:00+00:00")
    async with AsyncClient(
        transport=ASGITransport(app=postgres_app), base_url="http://test"
    ) as client:
        intro = await create_type(client, 60)
        response = await client.post(
            "/api/bookings", json={**booking_payload(event_type=intro), **change}
        )
        assert response.status_code == status
        assert response.json()["code"] == code
        assert_contract_response(response)
        assert (
            await client.post("/api/bookings", json=booking_payload(event_type=intro))
        ).status_code == 201


async def test_same_type_repeat_conflicts_and_no_public_booking_lookup(
    postgres_app: FastAPI,
) -> None:
    postgres_app.state.clock = lambda: datetime.fromisoformat("2026-11-04T05:00:00+00:00")
    async with AsyncClient(
        transport=ASGITransport(app=postgres_app), base_url="http://test"
    ) as client:
        intro = await create_type(client)
        saved = await client.post("/api/bookings", json=booking_payload(event_type=intro))
        again = await client.post("/api/bookings", json=booking_payload(event_type=intro))
        assert again.status_code == 409
        assert_contract_response(again)
        assert (await client.get("/api/bookings/" + saved.json()["id"])).status_code == 404


async def competing_requests(
    app: FastAPI, database_url: str, payloads: list[dict[str, Any]], *, advance_clock: bool = False
) -> list[Response]:
    """Establish real lock waits on distinct backends before allowing any winner."""
    import asyncio

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(database_url)
    observer_engine = create_async_engine(database_url, isolation_level="AUTOCOMMIT")
    tasks = []
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            async with engine.connect() as blocker, observer_engine.connect() as observer:
                transaction = await blocker.begin()
                blocker_pid = await blocker.scalar(text("SELECT pg_backend_pid()"))
                await blocker.execute(text("SELECT id FROM calendars WHERE id = 1 FOR UPDATE"))
                gate = asyncio.Event()

                async def send(payload: dict[str, Any]) -> Response:
                    await gate.wait()
                    return await client.post("/api/bookings", json=payload)

                tasks = [asyncio.create_task(send(payload)) for payload in payloads]
                gate.set()
                try:
                    async with asyncio.timeout(8):
                        while True:
                            rows = (
                                (
                                    await observer.execute(
                                        text(
                                            "SELECT pid, application_name, wait_event_type, "
                                            "pg_blocking_pids(pid) AS blockers "
                                            "FROM pg_stat_activity "
                                            "WHERE datname = current_database()"
                                        )
                                    )
                                )
                                .mappings()
                                .all()
                            )
                            graph = {row["pid"]: row["blockers"] for row in rows}

                            def blocked_by(
                                pid: int, visited: set[int], parents: dict[int, list[int]]
                            ) -> bool:
                                if pid == blocker_pid:
                                    return True
                                if pid in visited:
                                    return False
                                return any(
                                    blocked_by(parent, visited | {pid}, parents)
                                    for parent in parents.get(pid, [])
                                )

                            waiters = {
                                row["pid"]
                                for row in rows
                                if row["application_name"].startswith("booking-test-")
                                and row["wait_event_type"] == "Lock"
                                and blocked_by(row["pid"], set(), graph)
                            }
                            if len(waiters) == len(payloads):
                                break
                            await asyncio.sleep(0.02)
                    if advance_clock:
                        app.state.clock = lambda: datetime.fromisoformat(
                            "2026-11-04T07:00:00+00:00"
                        )
                except TimeoutError:
                    pytest.fail(
                        "HTTP concurrency was not established: distinct PostgreSQL backends "
                        "did not wait on the common calendar lock"
                    )
                finally:
                    await transaction.rollback()
                async with asyncio.timeout(10):
                    return await asyncio.gather(*tasks)
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        await observer_engine.dispose()
        await engine.dispose()


@pytest.mark.parametrize(
    "other_start,other_type,expected",
    [
        ("07:00", "intro", [201, 409]),
        ("07:30", "other", [201, 409]),
        ("08:00", "other", [201, 201]),
    ],
)
async def test_concurrent_bookings_use_independent_waiting_connections(
    postgres_app: FastAPI,
    test_database_url: str,
    other_start: str,
    other_type: str,
    expected: list[int],
) -> None:
    postgres_app.state.clock = lambda: datetime.fromisoformat("2026-11-04T05:00:00+00:00")
    async with AsyncClient(
        transport=ASGITransport(app=postgres_app), base_url="http://test"
    ) as client:
        intro = await create_type(client, 60)
        other = await add_type(client, "other", 30)
        for id in (intro, other):
            available = await client.get(f"/api/event-types/{id}/slots")
            assert "2026-11-04T07:00:00Z" in available.text
    responses = await competing_requests(
        postgres_app,
        test_database_url,
        [
            booking_payload(event_type=intro),
            booking_payload(
                f"2026-11-04T{other_start}:00Z", intro if other_type == "intro" else other
            ),
        ],
    )
    assert sorted(response.status_code for response in responses) == expected
    for response in responses:
        assert_contract_response(response)
        if response.status_code == 409:
            assert response.json()["code"] == "TIME_CONFLICT"
    async with AsyncClient(
        transport=ASGITransport(app=postgres_app), base_url="http://test"
    ) as client:
        stored = await client.get(
            "/api/organizer/bookings",
        )
        assert_contract_response(stored)
        assert {item["id"] for item in stored.json()["items"]} == {
            response.json()["id"] for response in responses if response.status_code == 201
        }
        assert len(stored.json()["items"]) == expected.count(201)
        # Every successful HTTP confirmation remains occupied after all transactions finished.
        for response in responses:
            if response.status_code == 201:
                public = await client.get(
                    f"/api/event-types/{response.json()['eventType']['id']}/slots"
                )
                assert response.json()["startsAt"] not in [
                    slot["startsAt"] for day in public.json()["days"] for slot in day["slots"]
                ]


async def test_clock_is_rechecked_after_waiting_for_the_calendar(
    postgres_app: FastAPI, test_database_url: str
) -> None:
    postgres_app.state.clock = lambda: datetime.fromisoformat("2026-11-04T05:00:00+00:00")
    async with AsyncClient(
        transport=ASGITransport(app=postgres_app), base_url="http://test"
    ) as client:
        intro = await create_type(client)
    responses = await competing_requests(
        postgres_app, test_database_url, [booking_payload(event_type=intro)], advance_clock=True
    )
    assert responses[0].status_code == 422
    assert responses[0].json()["code"] == "SLOT_NOT_BOOKABLE"
    assert_contract_response(responses[0])


async def test_storage_constraint_rejects_bypass_overlap_but_allows_adjacency(
    postgres_app: FastAPI, test_database_url: str
) -> None:
    from uuid import uuid4

    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError
    from sqlalchemy.ext.asyncio import create_async_engine

    async with AsyncClient(
        transport=ASGITransport(app=postgres_app), base_url="http://test"
    ) as client:
        intro = await create_type(client, 60)
        other = await add_type(client, "other", 30)
    engine = create_async_engine(test_database_url)
    statement = text(
        "INSERT INTO bookings (id,event_type_id,starts_at,ends_at,"
        "guest_name,guest_email,guest_comment) "
        "VALUES (:id,:type,CAST(:start AS timestamptz),CAST(:end AS timestamptz),"
        "'Guest','a@example.com','')"
    )

    async def insert(start: str | None, end: str, type: str = other) -> None:
        async with engine.begin() as connection:
            await connection.execute(
                statement, {"id": uuid4(), "type": type, "start": start, "end": end}
            )

    try:
        await insert("2026-11-04T07:00:00Z", "2026-11-04T08:00:00Z", intro)
        with pytest.raises(IntegrityError) as caught:
            await insert("2026-11-04T07:30:00Z", "2026-11-04T08:00:00Z")
        assert isinstance(caught.value.orig, Error)
        assert caught.value.orig.sqlstate == "23P01"
        assert caught.value.orig.diag.constraint_name == "ex_bookings_overlap"
        await insert("2026-11-04T08:00:00Z", "2026-11-04T08:30:00Z")
        for start, end in [
            ("2026-11-04T09:00:00Z", "2026-11-04T09:00:00Z"),
            ("2026-11-04T10:00:00Z", "2026-11-04T09:00:00Z"),
            ("-infinity", "2026-11-04T06:00:00Z"),
            ("2026-11-04T09:00:00Z", "infinity"),
            (None, "2026-11-04T09:00:00Z"),
        ]:
            with pytest.raises(IntegrityError):
                await insert(start, end)
        async with engine.connect() as connection:
            assert (
                await connection.execute(
                    text(
                        "SELECT condeferrable, condeferred FROM pg_constraint "
                        "WHERE conname='ex_bookings_overlap'"
                    )
                )
            ).one() == (False, False)
    finally:
        await engine.dispose()


async def test_booking_database_unavailable_matches_contract(test_database_url: str) -> None:
    from sqlalchemy.engine import make_url

    from backend.app.config import Settings
    from backend.app.main import create_app

    app = create_app(
        Settings(
            database_url=make_url(test_database_url)
            .set(port=1)
            .render_as_string(hide_password=False)
        )
    )
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        response = await client.post("/api/bookings", json=booking_payload())
        assert response.status_code == 503
        assert_contract_response(response)
        assert "127.0.0.1" not in response.text
        assert "postgresql" not in response.text


async def test_local_window_and_repeated_instants_are_bookable(postgres_app: FastAPI) -> None:
    from backend.tests.test_slots import set_timezone

    await set_timezone(postgres_app, "Pacific/Kwajalein")
    postgres_app.state.clock = lambda: datetime.fromisoformat("1969-09-29T13:00:00+00:00")
    async with AsyncClient(
        transport=ASGITransport(app=postgres_app), base_url="http://test"
    ) as client:
        intro = await create_type(client)
        for start in ["1969-09-29T22:00:00Z", "1969-09-30T21:00:00Z"]:
            response = await client.post("/api/bookings", json=booking_payload(start, intro))
            assert response.status_code == 201
            assert response.json()["startsAt"] == start
            assert_contract_response(response)


async def test_expired_window_is_rejected_even_if_previously_advertised(
    postgres_app: FastAPI,
) -> None:
    postgres_app.state.clock = lambda: datetime.fromisoformat("2026-11-04T05:00:00+00:00")
    async with AsyncClient(
        transport=ASGITransport(app=postgres_app), base_url="http://test"
    ) as client:
        intro = await create_type(client)
        assert "2026-11-04T07:00:00Z" in (await client.get(f"/api/event-types/{intro}/slots")).text
        postgres_app.state.clock = lambda: datetime.fromisoformat("2026-11-04T21:00:00+00:00")
        response = await client.post("/api/bookings", json=booking_payload(event_type=intro))
        assert response.status_code == 422
        assert response.json()["code"] == "SLOT_NOT_BOOKABLE"
        assert_contract_response(response)
