import logging

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.api.routes import analytics, athletes, auth, predictions, workouts
from app.core.config import settings

logger = logging.getLogger(__name__)

app = FastAPI(
    title=settings.PROJECT_NAME,
    version="0.1.0",
    description=(
        "A rowing performance analytics platform: workout analysis, pacing, "
        "heart-rate response, efficiency, training load, trends, personal "
        "bests, and 2K prediction as one advanced feature among many."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Error handling (spec section 40) ---
#
# FastAPI/Pydantic already return well-structured 422s for request
# validation errors and our routes raise HTTPException with meaningful
# status codes for expected failure cases (auth, ownership, not-found,
# bad CSV). These handlers cover what's left: making sure NOTHING ever
# escapes as a raw traceback or an inconsistent error shape, regardless
# of where it originates.


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": "The request body didn't match the expected format.", "errors": exc.errors()},
    )


@app.exception_handler(SQLAlchemyError)
async def database_exception_handler(request: Request, exc: SQLAlchemyError) -> JSONResponse:
    logger.error("Unhandled database error on %s %s", request.method, request.url.path, exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"detail": "A database error occurred. Please try again."},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    if isinstance(exc, HTTPException):
        # Should already be handled by Starlette's default handler, but
        # if it ever reaches here, preserve its intended status/detail
        # rather than masking it as a generic 500.
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    logger.error("Unhandled exception on %s %s", request.method, request.url.path, exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Something went wrong on our end. Please try again."},
    )


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    """Liveness/readiness probe used by Docker Compose's healthcheck."""
    return {"status": "ok"}


app.include_router(auth.router, prefix=settings.API_V1_PREFIX)
app.include_router(athletes.router, prefix=settings.API_V1_PREFIX)
app.include_router(workouts.router, prefix=settings.API_V1_PREFIX)
app.include_router(analytics.router, prefix=settings.API_V1_PREFIX)
app.include_router(predictions.router, prefix=settings.API_V1_PREFIX)


@app.on_event("startup")
def on_startup() -> None:
    """
    Dev/test convenience: ensure tables exist on startup.

    In a production deployment this would be replaced by running Alembic
    migrations before the app starts, but for this project's scope
    create_all() keeps local/demo setup to a single `docker compose up`.

    Failures here are logged rather than raised: the test suite overrides
    the `get_db` dependency with an isolated SQLite database and does not
    need this step to succeed against the real DATABASE_URL, and a
    transient DB connection hiccup shouldn't crash app startup entirely
    (Docker Compose's healthcheck/retries handle real outages).
    """
    from app.db.session import create_all_tables

    try:
        create_all_tables()
    except Exception:  # noqa: BLE001
        logger.warning("Could not create tables on startup; continuing.", exc_info=True)
