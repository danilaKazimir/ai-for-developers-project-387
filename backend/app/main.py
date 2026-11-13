from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import InterfaceError, OperationalError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.app.bookings import router as bookings_router
from backend.app.config import Settings
from backend.app.db import get_session
from backend.app.event_types import router
from backend.app.generated.models import ApiError, HealthStatus


def create_app(settings: Settings | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        config = settings if settings is not None else Settings()
        app.state.settings = config
        app.state.clock = lambda: datetime.now(UTC)
        engine = create_async_engine(
            config.database_url,
            pool_pre_ping=True,
            isolation_level="READ COMMITTED",
            connect_args={"connect_timeout": 3},
        )
        app.state.session_factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            yield
        finally:
            await engine.dispose()

    app = FastAPI(title="Call Calendar API", version="0.1.0", lifespan=lifespan)

    @app.middleware("http")
    async def private_organizer_responses(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        if request.url.path.startswith("/api/organizer/"):
            response.headers["Cache-Control"] = "private, no-store"
        return response

    app.include_router(router)
    app.include_router(bookings_router)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, error: HTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=error.status_code, content=error.detail, headers=error.headers
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, error: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "code": "VALIDATION_ERROR",
                "message": (
                    "Проверьте поля формы: время с часовым поясом, имя (1–120 символов), "
                    "email (до 254), комментарий или описание (до 2000) и длительность (1–540)."
                ),
            },
        )

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, error: SQLAlchemyError) -> JSONResponse:
        unavailable = isinstance(error, (OperationalError, InterfaceError))
        return JSONResponse(
            status_code=503 if unavailable else 500,
            content={
                "code": "DATABASE_UNAVAILABLE" if unavailable else "INTERNAL_ERROR",
                "message": "Сервис временно недоступен. Повторите попытку позже"
                if unavailable
                else "Не удалось выполнить запрос.",
            },
        )

    @app.exception_handler(Exception)
    async def internal_error(request: Request, error: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            headers={"Cache-Control": "private, no-store"}
            if request.url.path.startswith("/api/organizer/")
            else None,
            content={
                "code": "INTERNAL_ERROR",
                "message": "Не удалось выполнить запрос.",
            },
        )

    @app.get(
        "/api/health",
        operation_id="getHealth",
        response_model=HealthStatus,
        responses={503: {"model": ApiError}},
    )
    async def get_health(
        session: Annotated[AsyncSession, Depends(get_session)],
    ) -> HealthStatus | JSONResponse:
        try:
            await session.execute(text("SELECT 1"))
        except SQLAlchemyError:
            error = ApiError(
                code="DATABASE_UNAVAILABLE",
                message="Сервис временно недоступен. Повторите попытку позже",
            )
            return JSONResponse(status_code=503, content=error.model_dump(mode="json"))
        return HealthStatus(status="ok", database="ok")

    dist = Path(__file__).resolve().parents[2] / "dist"
    if (dist / "index.html").is_file():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        async def frontend() -> FileResponse:
            return FileResponse(dist / "index.html")

        for path in (
            "/",
            "/calendars/new",
            "/organizer/event-types/new",
            "/organizer/bookings",
            "/event-types",
            "/event-types/{event_type_id}",
        ):
            app.add_api_route(path, frontend, include_in_schema=False)

        @app.get("/favicon.svg", include_in_schema=False)
        async def favicon() -> FileResponse:
            return FileResponse(dist / "favicon.svg")

    return app
