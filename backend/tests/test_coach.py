import io

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.coach import CoachAthleteAssignment, WorkoutComment
from app.models.prediction import Prediction
from app.models.user import User, UserRole
from app.models.workout import Workout

PASSWORD = "correct-horse-battery-staple"
CSV = """Date,Time,Distance,Pace,SPM,HR
2026-09-01,1:47.0,500,1:47.0,28,158
2026-09-01,1:46.2,500,1:46.2,29,164
2026-09-01,1:44.8,500,1:44.8,30,170
2026-09-01,1:42.5,500,1:42.5,32,178
"""


def _register_athlete(client: TestClient, email: str):
    response = client.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD})
    assert response.status_code == 201
    body = response.json()
    return body, {"Authorization": f"Bearer {body['access_token']}"}


def _create_coach(client: TestClient, db: Session, email: str = "coach@example.com"):
    coach = User(
        email=email,
        hashed_password=hash_password(PASSWORD),
        role=UserRole.COACH,
        display_name="Coach Carter",
    )
    db.add(coach)
    db.commit()
    db.refresh(coach)
    response = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200
    return coach, response.json(), {"Authorization": f"Bearer {response.json()['access_token']}"}


def _upload(client: TestClient, headers: dict[str, str]) -> dict:
    response = client.post(
        "/api/v1/workouts/upload",
        headers=headers,
        files={"file": ("workout.csv", io.BytesIO(CSV.encode()), "text/csv")},
    )
    assert response.status_code == 201
    return response.json()["workouts"][0]


def _assign(db: Session, coach_id: int, athlete_id: int) -> CoachAthleteAssignment:
    assignment = CoachAthleteAssignment(coach_id=coach_id, athlete_id=athlete_id)
    db.add(assignment)
    db.commit()
    db.refresh(assignment)
    return assignment


def test_coach_login_has_no_synthetic_athlete(client: TestClient, db_session: Session) -> None:
    _coach, body, _headers = _create_coach(client, db_session)
    assert body["user"]["role"] == "coach"
    assert body["user"]["display_name"] == "Coach Carter"
    assert body["athlete"] is None
    assert db_session.query(User).filter(User.role == UserRole.COACH).count() == 1


def test_assigned_scope_and_unassigned_idor_are_enforced(client: TestClient, db_session: Session) -> None:
    athlete_a, _headers_a = _register_athlete(client, "a@example.com")
    athlete_b, _headers_b = _register_athlete(client, "b@example.com")
    coach, _body, coach_headers = _create_coach(client, db_session)
    _assign(db_session, coach.id, athlete_a["athlete"]["id"])

    listed = client.get("/api/v1/coach/athletes", headers=coach_headers)
    assert listed.status_code == 200
    assert [item["athlete"]["id"] for item in listed.json()] == [athlete_a["athlete"]["id"]]

    allowed = client.get(
        f"/api/v1/coach/athletes/{athlete_a['athlete']['id']}", headers=coach_headers
    )
    forbidden = client.get(
        f"/api/v1/coach/athletes/{athlete_b['athlete']['id']}", headers=coach_headers
    )
    assert allowed.status_code == 200
    assert forbidden.status_code == 404


def test_coach_cannot_use_athlete_write_endpoints(client: TestClient, db_session: Session) -> None:
    athlete_body, athlete_headers = _register_athlete(client, "rower@example.com")
    workout = _upload(client, athlete_headers)
    coach, _body, coach_headers = _create_coach(client, db_session)
    _assign(db_session, coach.id, athlete_body["athlete"]["id"])

    assert client.patch(
        f"/api/v1/athletes/{athlete_body['athlete']['id']}",
        headers=coach_headers,
        json={"weight_kg": 99},
    ).status_code == 403
    assert client.delete(f"/api/v1/workouts/{workout['id']}", headers=coach_headers).status_code == 403
    assert client.post(
        "/api/v1/workouts/upload",
        headers=coach_headers,
        files={"file": ("workout.csv", io.BytesIO(CSV.encode()), "text/csv")},
    ).status_code == 403
    assert db_session.get(Workout, workout["id"]) is not None


def test_comment_permissions_and_athlete_visibility(client: TestClient, db_session: Session) -> None:
    athlete_body, athlete_headers = _register_athlete(client, "rower@example.com")
    other_body, _other_headers = _register_athlete(client, "other@example.com")
    workout = _upload(client, athlete_headers)
    coach, _body, coach_headers = _create_coach(client, db_session)

    denied = client.post(
        f"/api/v1/coach/athletes/{athlete_body['athlete']['id']}/workouts/{workout['id']}/comments",
        headers=coach_headers,
        json={"body": "Not assigned"},
    )
    assert denied.status_code == 404

    assignment = _assign(db_session, coach.id, athlete_body["athlete"]["id"])
    created = client.post(
        f"/api/v1/coach/athletes/{athlete_body['athlete']['id']}/workouts/{workout['id']}/comments",
        headers=coach_headers,
        json={"body": "Good consistency across the intervals."},
    )
    assert created.status_code == 201
    assert created.json()["coach_name"] == "Coach Carter"

    visible = client.get(f"/api/v1/workouts/{workout['id']}/comments", headers=athlete_headers)
    assert visible.status_code == 200
    assert visible.json()[0]["body"].startswith("Good consistency")

    db_session.delete(assignment)
    db_session.commit()
    assert db_session.query(WorkoutComment).count() == 1
    assert client.get(
        f"/api/v1/coach/athletes/{athlete_body['athlete']['id']}/workouts/{workout['id']}",
        headers=coach_headers,
    ).status_code == 404
    assert client.get(f"/api/v1/workouts/{workout['id']}/comments", headers=athlete_headers).status_code == 200


def test_report_is_pdf_and_unassigned_report_is_hidden(client: TestClient, db_session: Session) -> None:
    athlete_body, athlete_headers = _register_athlete(client, "rower@example.com")
    _upload(client, athlete_headers)
    coach, _body, coach_headers = _create_coach(client, db_session)

    hidden = client.get(
        f"/api/v1/coach/athletes/{athlete_body['athlete']['id']}/report.pdf",
        headers=coach_headers,
    )
    assert hidden.status_code == 404

    _assign(db_session, coach.id, athlete_body["athlete"]["id"])
    response = client.get(
        f"/api/v1/coach/athletes/{athlete_body['athlete']['id']}/report.pdf?start_date=2026-08-01&end_date=2026-09-30",
        headers=coach_headers,
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["cache-control"] == "private, no-store"
    assert response.content.startswith(b"%PDF")
    assert len(response.content) > 1500


def test_coach_prediction_does_not_persist(client: TestClient, db_session: Session) -> None:
    athlete_body, athlete_headers = _register_athlete(client, "rower@example.com")
    _upload(client, athlete_headers)
    coach, _body, coach_headers = _create_coach(client, db_session)
    _assign(db_session, coach.id, athlete_body["athlete"]["id"])

    before = db_session.query(Prediction).count()
    response = client.get(
        f"/api/v1/coach/athletes/{athlete_body['athlete']['id']}/predictions/2k",
        headers=coach_headers,
    )
    assert response.status_code == 200
    assert db_session.query(Prediction).count() == before
