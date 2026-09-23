from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


def test_coach_migration_upgrades_legacy_database(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    with engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE users (id INTEGER PRIMARY KEY, email VARCHAR(255) NOT NULL UNIQUE, "
            "hashed_password VARCHAR(255) NOT NULL, created_at DATETIME NOT NULL)"
        ))
        connection.execute(text(
            "CREATE TABLE athletes (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, "
            "name VARCHAR(255) NOT NULL)"
        ))
        connection.execute(text(
            "CREATE TABLE workouts (id INTEGER PRIMARY KEY, athlete_id INTEGER NOT NULL, "
            "title VARCHAR(255) NOT NULL)"
        ))
        connection.execute(text(
            "INSERT INTO users (id, email, hashed_password, created_at) "
            "VALUES (1, 'legacy@example.com', 'hash', CURRENT_TIMESTAMP)"
        ))

        config = Config("alembic.ini")
        config.attributes["connection"] = connection
        command.upgrade(config, "head")

        inspector = inspect(connection)
        assert {"role", "display_name"}.issubset(
            {column["name"] for column in inspector.get_columns("users")}
        )
        assert "coach_athlete_assignments" in inspector.get_table_names()
        assert "workout_comments" in inspector.get_table_names()
        assert "coach_athlete_invitations" in inspector.get_table_names()
        assert connection.execute(text("SELECT role FROM users WHERE id = 1")).scalar_one() == "athlete"
