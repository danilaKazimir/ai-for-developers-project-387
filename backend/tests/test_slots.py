from datetime import datetime

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from backend.tests.contract import assert_contract_response

pytestmark = pytest.mark.integration


async def create_type(client: AsyncClient, duration: int = 30) -> str:
    response = await client.post(
        "/api/organizer/event-types",
        json={
            "name": "Знакомство",
            "description": "Обсудим задачу",
            "durationMinutes": duration,
        },
    )
    assert response.status_code == 201
    return str(response.json()["id"])


@pytest.mark.parametrize("now", ["2026-11-04T06:30:00+00:00", "2026-11-04T09:30:00+03:00"])
async def test_calendar_returns_fourteen_local_dates_and_future_weekday_starts(
    postgres_app: FastAPI,
    now: str,
) -> None:
    postgres_app.state.clock = lambda: datetime.fromisoformat(now)
    async with AsyncClient(
        transport=ASGITransport(app=postgres_app), base_url="http://test"
    ) as client:
        intro = await create_type(client)
        response = await client.get(f"/api/event-types/{intro}/slots")
    assert response.status_code == 200
    assert_contract_response(response)
    calendar = response.json()
    assert calendar["eventType"] == {
        "id": intro,
        "name": "Знакомство",
        "description": "Обсудим задачу",
        "durationMinutes": 30,
    }
    assert calendar["timezone"] == "Europe/Moscow"
    assert calendar["windowStartDate"] == "2026-11-04"
    assert calendar["windowEndDateExclusive"] == "2026-11-18"
    assert [day["date"] for day in calendar["days"]] == [
        "2026-11-04",
        "2026-11-05",
        "2026-11-06",
        "2026-11-07",
        "2026-11-08",
        "2026-11-09",
        "2026-11-10",
        "2026-11-11",
        "2026-11-12",
        "2026-11-13",
        "2026-11-14",
        "2026-11-15",
        "2026-11-16",
        "2026-11-17",
    ]
    assert calendar["days"][0]["slots"][0] == {
        "startsAt": "2026-11-04T07:00:00Z",
        "endsAt": "2026-11-04T07:30:00Z",
    }
    assert calendar["days"][0]["slots"][-1] == {
        "startsAt": "2026-11-04T14:30:00Z",
        "endsAt": "2026-11-04T15:00:00Z",
    }
    assert len(calendar["days"][1]["slots"]) == 18
    assert [calendar["days"][i]["slots"] for i in (3, 4, 10, 11)] == [[], [], [], []]


@pytest.mark.parametrize(
    "duration,last_start,count",
    [(30, "14:30", 18), (45, "14:00", 17), (60, "14:00", 17), (540, "06:00", 1)],
)
async def test_entire_meeting_fits_workday(
    postgres_app: FastAPI,
    duration: int,
    last_start: str,
    count: int,
) -> None:
    postgres_app.state.clock = lambda: datetime.fromisoformat("2026-11-04T05:59:59+00:00")
    async with AsyncClient(
        transport=ASGITransport(app=postgres_app), base_url="http://test"
    ) as client:
        intro = await create_type(client, duration)
        response = await client.get(f"/api/event-types/{intro}/slots")
    assert_contract_response(response)
    slots = response.json()["days"][0]["slots"]
    assert len(slots) == count
    assert slots[0]["startsAt"] == "2026-11-04T06:00:00Z"
    assert slots[-1]["startsAt"] == f"2026-11-04T{last_start}:00Z"
    assert slots[-1]["endsAt"] == (
        "2026-11-04T14:45:00Z" if duration == 45 else "2026-11-04T15:00:00Z"
    )


async def test_window_rolls_at_calendar_midnight_not_utc(postgres_app: FastAPI) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=postgres_app), base_url="http://test"
    ) as client:
        intro = await create_type(client)
        postgres_app.state.clock = lambda: datetime.fromisoformat("2026-11-03T20:59:59+00:00")
        before = await client.get(f"/api/event-types/{intro}/slots")
        postgres_app.state.clock = lambda: datetime.fromisoformat("2026-11-03T21:00:00+00:00")
        after = await client.get(f"/api/event-types/{intro}/slots")
    assert before.json()["windowStartDate"] == "2026-11-03"
    assert before.json()["days"][0]["slots"] == []
    assert before.json()["days"][-1]["date"] == "2026-11-16"
    assert after.json()["windowStartDate"] == "2026-11-04"
    assert after.json()["windowEndDateExclusive"] == "2026-11-18"
    assert after.json()["days"][0]["slots"][0]["startsAt"] == "2026-11-04T06:00:00Z"
    for response in (before, after):
        assert_contract_response(response)


async def test_unknown_type_returns_declared_error(postgres_app: FastAPI) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=postgres_app), base_url="http://test"
    ) as client:
        response = await client.get("/api/event-types/missing/slots")
    assert response.status_code == 404
    assert response.json()["code"] == "EVENT_TYPE_NOT_FOUND"
    assert_contract_response(response)


async def set_timezone(app: FastAPI, timezone: str) -> None:
    from sqlalchemy import text

    async with app.state.session_factory() as session:
        await session.execute(
            text("UPDATE calendars SET timezone = :zone WHERE id = 1"), {"zone": timezone}
        )
        await session.commit()


@pytest.mark.parametrize(
    "now,start,end,first,last",
    [
        (
            "2026-03-02T05:00:00+00:00",
            "2026-03-02",
            "2026-03-16",
            "2026-03-02T14:00:00Z",
            "2026-03-13T13:00:00Z",
        ),
        (
            "2026-10-26T04:00:00+00:00",
            "2026-10-26",
            "2026-11-09",
            "2026-10-26T13:00:00Z",
            "2026-11-06T14:00:00Z",
        ),
    ],
)
async def test_dst_window_uses_local_dates_and_current_offset(
    postgres_app: FastAPI,
    now: str,
    start: str,
    end: str,
    first: str,
    last: str,
) -> None:
    await set_timezone(postgres_app, "America/New_York")
    postgres_app.state.clock = lambda: datetime.fromisoformat(now)
    async with AsyncClient(
        transport=ASGITransport(app=postgres_app), base_url="http://test"
    ) as client:
        intro = await create_type(client)
        response = await client.get(f"/api/event-types/{intro}/slots")
    assert_contract_response(response)
    calendar = response.json()
    assert calendar["windowStartDate"] == start
    assert calendar["windowEndDateExclusive"] == end
    assert len(calendar["days"]) == 14
    assert calendar["days"][0]["slots"][0]["startsAt"] == first
    assert calendar["days"][11]["slots"][0]["startsAt"] == last


async def test_nonexistent_weekday_is_returned_without_normalized_slots(
    postgres_app: FastAPI,
) -> None:
    await set_timezone(postgres_app, "Pacific/Apia")
    postgres_app.state.clock = lambda: datetime.fromisoformat("2011-12-29T10:00:00+00:00")
    async with AsyncClient(
        transport=ASGITransport(app=postgres_app), base_url="http://test"
    ) as client:
        intro = await create_type(client)
        response = await client.get(f"/api/event-types/{intro}/slots")
    assert_contract_response(response)
    calendar = response.json()
    assert calendar["days"][1] == {"date": "2011-12-30", "slots": []}
    assert calendar["windowEndDateExclusive"] == "2012-01-12"
    assert calendar["days"][4]["slots"][0]["startsAt"] == "2012-01-01T19:00:00Z"


async def test_repeated_weekday_keeps_both_instants_in_real_order(postgres_app: FastAPI) -> None:
    await set_timezone(postgres_app, "Pacific/Kwajalein")
    postgres_app.state.clock = lambda: datetime.fromisoformat("1969-09-29T13:00:00+00:00")
    async with AsyncClient(
        transport=ASGITransport(app=postgres_app), base_url="http://test"
    ) as client:
        intro = await create_type(client)
        response = await client.get(f"/api/event-types/{intro}/slots")
    assert_contract_response(response)
    slots = response.json()["days"][0]["slots"]
    assert len(slots) == 36
    assert slots[0] == {"startsAt": "1969-09-29T22:00:00Z", "endsAt": "1969-09-29T22:30:00Z"}
    assert slots[17]["endsAt"] == "1969-09-30T07:00:00Z"
    assert slots[18] == {"startsAt": "1969-09-30T21:00:00Z", "endsAt": "1969-09-30T21:30:00Z"}
    assert slots[-1]["endsAt"] == "1969-10-01T06:00:00Z"


async def test_malformed_event_type_path_is_validation_error(postgres_app: FastAPI) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=postgres_app), base_url="http://test"
    ) as client:
        response = await client.get("/api/event-types/Bad--id/slots")
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"
    assert_contract_response(response)
