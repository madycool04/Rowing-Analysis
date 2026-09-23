"""Controlled coach account and assignment administration.

Examples:
  python -m scripts.coach_admin create-coach --email coach@example.com --name "Coach Carter"
  python -m scripts.coach_admin assign --coach coach@example.com --athlete athlete@example.com
  python -m scripts.coach_admin unassign --coach coach@example.com --athlete athlete@example.com
"""
from __future__ import annotations

import argparse
from getpass import getpass

from sqlalchemy import func

from app.core.security import hash_password
from app.db.session import SessionLocal, import_all_models
from app.models.athlete import Athlete
from app.models.coach import CoachAthleteAssignment
from app.models.user import User, UserRole


# SQLAlchemy resolves string relationship targets (for example
# Athlete.workouts -> Workout) when the first query configures the mappers.
# Administrative scripts do not import the FastAPI app, so register every
# model explicitly before opening a session or issuing a query.
import_all_models()


def _email(value: str) -> str:
    return value.strip().lower()


def create_coach(args) -> None:
    password = args.password or getpass("Coach password: ")
    if len(password) < 8:
        raise SystemExit("Password must contain at least 8 characters.")
    with SessionLocal() as db:
        if db.query(User).filter(func.lower(User.email) == _email(args.email)).first():
            raise SystemExit("A user with that email already exists.")
        coach = User(
            email=_email(args.email),
            hashed_password=hash_password(password),
            role=UserRole.COACH,
            display_name=args.name.strip(),
        )
        db.add(coach)
        db.commit()
        print(f"Created coach {coach.display_name} <{coach.email}> (id={coach.id}).")


def _lookup(db, coach_email: str, athlete_email: str):
    coach = db.query(User).filter(func.lower(User.email) == _email(coach_email), User.role == UserRole.COACH).first()
    if coach is None:
        raise SystemExit("Coach account not found.")
    athlete_user = db.query(User).filter(func.lower(User.email) == _email(athlete_email), User.role == UserRole.ATHLETE).first()
    if athlete_user is None:
        raise SystemExit("Athlete account not found.")
    athlete = db.query(Athlete).filter(Athlete.user_id == athlete_user.id).order_by(Athlete.id.asc()).first()
    if athlete is None:
        raise SystemExit("Athlete profile not found.")
    return coach, athlete


def assign(args) -> None:
    with SessionLocal() as db:
        coach, athlete = _lookup(db, args.coach, args.athlete)
        existing = db.query(CoachAthleteAssignment).filter_by(coach_id=coach.id, athlete_id=athlete.id).first()
        if existing:
            print("Assignment already exists.")
            return
        db.add(CoachAthleteAssignment(coach_id=coach.id, athlete_id=athlete.id))
        db.commit()
        print(f"Assigned {athlete.name} to {coach.display_name or coach.email}.")


def unassign(args) -> None:
    with SessionLocal() as db:
        coach, athlete = _lookup(db, args.coach, args.athlete)
        assignment = db.query(CoachAthleteAssignment).filter_by(coach_id=coach.id, athlete_id=athlete.id).first()
        if assignment is None:
            print("Assignment does not exist.")
            return
        db.delete(assignment)
        db.commit()
        print(f"Removed assignment for {athlete.name} and {coach.display_name or coach.email}.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage OarSight coach accounts and assignments.")
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create-coach")
    create.add_argument("--email", required=True)
    create.add_argument("--name", required=True)
    create.add_argument("--password", help="Omit to enter it without shell history exposure.")
    create.set_defaults(func=create_coach)
    for command, handler in (("assign", assign), ("unassign", unassign)):
        item = sub.add_parser(command)
        item.add_argument("--coach", required=True, help="Coach account email")
        item.add_argument("--athlete", required=True, help="Athlete account email")
        item.set_defaults(func=handler)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
