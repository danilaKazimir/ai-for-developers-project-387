from datetime import datetime, timedelta
from typing import Annotated, Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import ConfigDict, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db import get_session
from backend.app.generated.models import (
    CreateEventTypeRequest,
    EventType,
    EventTypeCatalog,
    EventTypeSlots,
)
from backend.app.models import BookingRecord, Calendar, EventTypeRecord
from backend.app.scheduling import get_now, schedule_days

router = APIRouter()


class EventTypeInput(CreateEventTypeRequest):
    model_config = ConfigDict(extra="forbid", strict=True)

    @field_validator("name", mode="before")
    @classmethod
    def trim_name(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value


def event_type_response(record: EventTypeRecord) -> EventType:
    return EventType(
        id=record.id,
        name=record.name,
        description=record.description,
        durationMinutes=record.duration_minutes,
    )


@router.post(
    "/api/organizer/event-types",
    status_code=201,
    response_model=EventType,
    operation_id="createEventType",
)
async def create_event_type(
    body: EventTypeInput,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> EventType:
    for attempt in range(3):
        record = EventTypeRecord(
            id=uuid4().hex,
            name=body.name,
            description=body.description,
            duration_minutes=body.durationMinutes,
        )
        session.add(record)
        try:
            await session.commit()
        except IntegrityError as error:
            await session.rollback()
            original = error.orig
            collision = (
                getattr(original, "sqlstate", None) == "23505"
                and getattr(getattr(original, "diag", None), "constraint_name", None)
                == "event_types_pkey"
            )
            if not collision or attempt == 2:
                raise
        else:
            return event_type_response(record)
    raise RuntimeError("Event type creation exhausted")


@router.get("/api/event-types", response_model=EventTypeCatalog, operation_id="listEventTypes")
async def list_event_types(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> EventTypeCatalog:
    records = await session.scalars(select(EventTypeRecord).order_by(EventTypeRecord.id))
    return EventTypeCatalog(items=[event_type_response(record) for record in records])


@router.get(
    "/api/event-types/{eventTypeId}/slots",
    response_model=EventTypeSlots,
    operation_id="getEventTypeSlots",
)
async def get_event_type_slots(
    eventTypeId: Annotated[
        str, Path(min_length=1, max_length=64, pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
    now: Annotated[datetime, Depends(get_now)],
) -> EventTypeSlots:
    record = await session.get(EventTypeRecord, eventTypeId)
    if record is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "EVENT_TYPE_NOT_FOUND", "message": "Событие не найдено."},
        )
    calendar = await session.get(Calendar, 1)
    if calendar is None:
        raise RuntimeError("The common calendar has not been initialized")
    zone = ZoneInfo(calendar.timezone)
    today = now.astimezone(zone).date()
    days = schedule_days(record.duration_minutes, now, zone)
    candidates = [slot for day in days for slot in day.slots]
    if candidates:
        busy = list(
            await session.scalars(
                select(BookingRecord).where(
                    BookingRecord.starts_at < max(slot.endsAt for slot in candidates),
                    BookingRecord.ends_at > min(slot.startsAt for slot in candidates),
                )
            )
        )
        for day in days:
            day.slots = [
                slot
                for slot in day.slots
                if not any(
                    slot.startsAt < booking.ends_at and booking.starts_at < slot.endsAt
                    for booking in busy
                )
            ]
    return EventTypeSlots(
        eventType=event_type_response(record),
        timezone=calendar.timezone,
        windowStartDate=today,
        windowEndDateExclusive=today + timedelta(days=14),
        days=days,
    )
