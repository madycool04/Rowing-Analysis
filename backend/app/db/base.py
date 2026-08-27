from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """
    Shared declarative base for all ORM models (SQLAlchemy 2.x style).

    All models in app/models/* should inherit from this class. Importing
    this module does NOT import the models themselves - that happens in
    app/db/session.py's `import_all_models()` / Alembic env, so that
    `Base.metadata` is fully populated before `create_all` or autogenerate
    runs.
    """

    pass
