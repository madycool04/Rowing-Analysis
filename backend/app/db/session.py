from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True, future=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a request-scoped DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def import_all_models() -> None:
    """
    Ensure every ORM model module is imported so Base.metadata is complete
    before create_all()/Alembic autogenerate runs. Extended as models are
    added in later phases.
    """
    from app.models import user, athlete, workout, segment, split, prediction  # noqa: F401


def create_all_tables() -> None:
    """Dev/test convenience - creates tables directly without Alembic."""
    import_all_models()
    from app.db.base import Base

    Base.metadata.create_all(bind=engine)
