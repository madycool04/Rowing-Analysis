import io

from fastapi.testclient import TestClient

VALID_PASSWORD = "correct-horse-battery-staple"

CSV_2K = """Date,Time,Distance,Pace,HR
2026-06-01,1:47.0,500,1:47.0,158
2026-06-01,1:46.2,500,1:46.2,164
2026-06-01,1:44.8,500,1:44.8,170
2026-06-01,1:42.5,500,1:42.5,178
"""


def _auth_headers(client: TestClient, email: str = "rower@example.com") -> dict[str, str]:
    resp = client.post("/api/v1/auth/register", json={"email": email, "password": VALID_PASSWORD})
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _upload(client: TestClient, headers: dict[str, str]):
    return client.post(
        "/api/v1/workouts/upload",
        headers=headers,
        files={"file": ("workout.csv", io.BytesIO(CSV_2K.encode()), "text/csv")},
    )


class TestPredictionEndpoint:
    def test_requires_auth(self, client: TestClient) -> None:
        resp = client.get("/api/v1/predictions/2k")
        assert resp.status_code == 401

    def test_unavailable_with_no_workouts(self, client: TestClient) -> None:
        headers = _auth_headers(client)
        resp = client.get("/api/v1/predictions/2k", headers=headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["available"] is False

    def test_available_after_uploading_a_2k(self, client: TestClient) -> None:
        headers = _auth_headers(client)
        _upload(client, headers)
        resp = client.get("/api/v1/predictions/2k", headers=headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["available"] is True
        assert body["predicted_time_s"] is not None
        assert body["predicted_pace_display"] is not None
        assert body["confidence"] == "low"  # only one historical 2K

    def test_never_claims_guaranteed_performance(self, client: TestClient) -> None:
        headers = _auth_headers(client)
        _upload(client, headers)
        resp = client.get("/api/v1/predictions/2k", headers=headers)
        note = resp.json()["note"].lower()
        assert "not a guaranteed performance" in note

    def test_second_call_includes_change_vs_previous(self, client: TestClient) -> None:
        headers = _auth_headers(client)
        _upload(client, headers)
        first = client.get("/api/v1/predictions/2k", headers=headers).json()
        second = client.get("/api/v1/predictions/2k", headers=headers).json()
        assert first["change_vs_previous_s"] is None  # no prior prediction existed yet
        assert second["change_vs_previous_s"] is not None  # first call's prediction is now "previous"

    def test_scoped_to_own_athlete(self, client: TestClient) -> None:
        headers_a = _auth_headers(client, email="a@example.com")
        headers_b = _auth_headers(client, email="b@example.com")
        _upload(client, headers_a)

        resp_a = client.get("/api/v1/predictions/2k", headers=headers_a)
        resp_b = client.get("/api/v1/predictions/2k", headers=headers_b)

        assert resp_a.json()["available"] is True
        assert resp_b.json()["available"] is False
