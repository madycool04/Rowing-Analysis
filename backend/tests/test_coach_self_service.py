from fastapi.testclient import TestClient

PASSWORD = "correct-horse-battery-staple"


def _register(client: TestClient, email: str, role: str = "athlete", name: str | None = None):
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": PASSWORD, "role": role, "display_name": name},
    )
    assert response.status_code == 201
    body = response.json()
    return body, {"Authorization": f"Bearer {body['access_token']}"}


def test_coach_can_register_without_creating_athlete(client: TestClient) -> None:
    body, _headers = _register(client, "carter@example.com", role="coach", name="Coach Carter")
    assert body["user"]["role"] == "coach"
    assert body["user"]["display_name"] == "Coach Carter"
    assert body["athlete"] is None


def test_coach_registration_requires_display_name(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "coach@example.com", "password": PASSWORD, "role": "coach"},
    )
    assert response.status_code == 422


def test_invitation_requires_athlete_consent_and_can_disconnect(client: TestClient) -> None:
    athlete, athlete_headers = _register(client, "athlete@example.com")
    _coach, coach_headers = _register(client, "carter@example.com", role="coach", name="Coach Carter")
    athlete_id = athlete["athlete"]["id"]

    invitation_response = client.post(
        "/api/v1/coach/invitations",
        headers=coach_headers,
        json={"athlete_email": "athlete@example.com"},
    )
    assert invitation_response.status_code == 201
    invitation = invitation_response.json()
    assert invitation["coach_name"] == "Coach Carter"

    # Sending an invitation alone grants no athlete access.
    assert client.get(f"/api/v1/coach/athletes/{athlete_id}", headers=coach_headers).status_code == 404

    received = client.get("/api/v1/athlete/coaches/invitations", headers=athlete_headers)
    assert received.status_code == 200
    assert received.json()[0]["id"] == invitation["id"]

    accepted = client.post(
        f"/api/v1/athlete/coaches/invitations/{invitation['id']}/accept",
        headers=athlete_headers,
    )
    assert accepted.status_code == 200
    assert accepted.json()["coach_name"] == "Coach Carter"
    assert client.get(f"/api/v1/coach/athletes/{athlete_id}", headers=coach_headers).status_code == 200

    connected = client.get("/api/v1/athlete/coaches", headers=athlete_headers)
    assert connected.status_code == 200
    assert len(connected.json()) == 1

    disconnected = client.delete(
        f"/api/v1/athlete/coaches/{accepted.json()['coach_id']}", headers=athlete_headers
    )
    assert disconnected.status_code == 204
    assert client.get(f"/api/v1/coach/athletes/{athlete_id}", headers=coach_headers).status_code == 404


def test_athlete_can_reject_and_coach_can_cancel_invitation(client: TestClient) -> None:
    _athlete, athlete_headers = _register(client, "athlete@example.com")
    _coach, coach_headers = _register(client, "carter@example.com", role="coach", name="Coach Carter")

    first = client.post(
        "/api/v1/coach/invitations", headers=coach_headers, json={"athlete_email": "athlete@example.com"}
    ).json()
    assert client.post(
        f"/api/v1/athlete/coaches/invitations/{first['id']}/reject", headers=athlete_headers
    ).status_code == 204

    second = client.post(
        "/api/v1/coach/invitations", headers=coach_headers, json={"athlete_email": "athlete@example.com"}
    ).json()
    assert client.delete(f"/api/v1/coach/invitations/{second['id']}", headers=coach_headers).status_code == 204
    assert client.get("/api/v1/athlete/coaches/invitations", headers=athlete_headers).json() == []


def test_roles_cannot_cross_invitation_endpoints(client: TestClient) -> None:
    _athlete, athlete_headers = _register(client, "athlete@example.com")
    _coach, coach_headers = _register(client, "carter@example.com", role="coach", name="Coach Carter")
    assert client.post(
        "/api/v1/coach/invitations", headers=athlete_headers, json={"athlete_email": "athlete@example.com"}
    ).status_code == 403
    assert client.get("/api/v1/athlete/coaches/invitations", headers=coach_headers).status_code == 403
