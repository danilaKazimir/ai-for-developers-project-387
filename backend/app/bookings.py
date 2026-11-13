from datetime import UTC, datetime
from re import fullmatch
from typing import Annotated, Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db import get_session
from backend.app.event_types import event_type_response
from backend.app.generated.models import (
    BookingConfirmation,
    BookingGuest,
    CreateBookingRequest,
    OrganizerBooking,
    OrganizerBookings,
)
from backend.app.models import BOOKING_OVERLAP_CONSTRAINT, BookingRecord, Calendar, EventTypeRecord
from backend.app.scheduling import get_now, schedule_days

router = APIRouter()


class GuestInput(BookingGuest):
    @field_validator("name", mode="before")
    @classmethod
    def trim_name(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value

    @field_validator("comment", mode="before")
    @classmethod
    def reject_null_comment(cls, value: Any) -> Any:
        if value is None:
            raise ValueError("Omit an optional comment instead of sending null")
        return value


class BookingInput(CreateBookingRequest):
    guest: GuestInput

    @field_validator("startsAt", mode="before")
    @classmethod
    def require_timestamp_string(cls, value: Any) -> Any:
        if (
            not isinstance(value, str)
            or fullmatch(
                r"[0-9]{4}-[0-9]{2}-[0-9]{2}[Tt][0-9]{2}:[0-9]{2}:[0-9]{2}"
                r"(?:\.[0-9]+)?(?:[Zz]|[+-][0-9]{2}:[0-9]{2})",
                value,
            )
            is None
        ):
            raise ValueError("Use an RFC 3339 timestamp with offset")
        return value


def time_conflict() -> HTTPException:
    return HTTPException(
        409,
        detail={
            "code": "TIME_CONFLICT",
            "message": "Это время уже заняли. Выберите другое время",
        },
    )


@router.post(
    "/api/bookings",
    status_code=201,
    response_model=BookingConfirmation,
    operation_id="createBooking",
)
async def create_booking(
    body: BookingInput,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> BookingConfirmation:
    try:
        async with session.begin():
            calendar = await session.scalar(
                select(Calendar).where(Calendar.id == 1).with_for_update()
            )
            if calendar is None:
                raise RuntimeError("The common calendar has not been initialized")
            now = get_now(request)  # Read the actual clock only after the awaited common lock.
            record = await session.get(EventTypeRecord, body.eventTypeId)
            if record is None:
                raise HTTPException(
                    404,
                    detail={"code": "EVENT_TYPE_NOT_FOUND", "message": "Событие не найдено."},
                )
            start = body.startsAt.astimezone(UTC)
            selected = next(
                (
                    slot
                    for day in schedule_days(
                        record.duration_minutes, now, ZoneInfo(calendar.timezone)
                    )
                    for slot in day.slots
                    if slot.startsAt == start
                ),
                None,
            )
            if selected is None:
                raise HTTPException(
                    422,
                    detail={
                        "code": "SLOT_NOT_BOOKABLE",
                        "message": "Выбранное время больше недоступно. Выберите другое время",
                    },
                )
            # A separate statement sees the winner committed while this request waited.
            overlap = await session.scalar(
                select(BookingRecord.id)
                .where(
                    BookingRecord.starts_at < selected.endsAt,
                    BookingRecord.ends_at > start,
                )
                .limit(1)
            )
            if overlap is not None:
                raise time_conflict()
            booking = BookingRecord(
                event_type_id=record.id,
                starts_at=start,
                ends_at=selected.endsAt,
                guest_name=body.guest.name,
                guest_email=str(body.guest.email),
                guest_comment=body.guest.comment or "",
            )
            session.add(booking)
            await session.flush()
            result = BookingConfirmation(
                id=booking.id,
                eventType=event_type_response(record),
                startsAt=start,
                endsAt=selected.endsAt,
                timezone=calendar.timezone,
            )
        return result  # The transaction has committed before a successful response.
    except IntegrityError as error:
        original = error.orig  # The transaction context has already rolled back.
        if (
            getattr(original, "sqlstate", None) == "23P01"
            and getattr(getattr(original, "diag", None), "constraint_name", None)
            == BOOKING_OVERLAP_CONSTRAINT
        ):
            raise time_conflict() from error
        raise


@router.get(
    "/api/organizer/bookings",
    response_model=OrganizerBookings,
    operation_id="listOrganizerBookings",
)
async def list_organizer_bookings(
    session: Annotated[AsyncSession, Depends(get_session)],
    now: Annotated[datetime, Depends(get_now)],
) -> OrganizerBookings:
    calendar = await session.get(Calendar, 1)
    if calendar is None:
        raise RuntimeError("The common calendar has not been initialized")
    rows = await session.execute(
        select(BookingRecord, EventTypeRecord)
        .join(EventTypeRecord, BookingRecord.event_type_id == EventTypeRecord.id)
        .where(BookingRecord.starts_at >= now)
        .order_by(BookingRecord.starts_at, BookingRecord.id)
    )
    return OrganizerBookings(
        items=[
            OrganizerBooking(
                id=booking.id,
                eventType=event_type_response(event_type),
                startsAt=booking.starts_at.astimezone(UTC),
                endsAt=booking.ends_at.astimezone(UTC),
                timezone=calendar.timezone,
                guest=BookingGuest(
                    name=booking.guest_name,
                    email=booking.guest_email,
                    comment=booking.guest_comment,
                ),
            )
            for booking, event_type in rows
        ]
    )
