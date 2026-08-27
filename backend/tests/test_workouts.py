import io

from fastapi.testclient import TestClient

VALID_PASSWORD = "correct-horse-battery-staple"

DETAILED_CSV = """Date,Time,Distance,Pace,SPM,HR
2026-08-01,1:47.0,500,1:47.0,28,158
2026-08-01,1:46.2,500,1:46.2,29,164
2026-08-01,1:44.8,500,1:44.8,30,170
2026-08-01,1:42.5,500,1:42.5,32,178
"""

SUMMARY_CSV = """Date,Description,Time,Distance,Avg Heart Rate
2026-08-01,2K Test,7:05.2,2000,172
"""


def _auth_headers(client: TestClient, email: str = "rower@example.com") -> dict[str, str]:
    resp = client.post("/api/v1/auth/register", json={"email": email, "password": VALID_PASSWORD})
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _upload_csv(client: TestClient, headers: dict[str, str], content: str, filename: str = "workout.csv"):
    return client.post(
        "/api/v1/workouts/upload",
        headers=headers,
        files={"file": (filename, io.BytesIO(content.encode("utf-8")), "text/csv")},
    )


class TestUpload:
    def test_upload_detailed_csv_creates_workout_with_splits(self, client: TestClient) -> None:
        headers = _auth_headers(client)
        resp = _upload_csv(client, headers, DETAILED_CSV)
        assert resp.status_code == 201
        body = resp.json()

        workout = body["workout"]
        assert workout["has_splits"] is True
        assert workout["total_distance_m"] == 2000.0
        assert len(workout["segments"]) == 1
        assert len(workout["segments"][0]["splits"]) == 4

    def test_upload_summary_csv_creates_workout_without_splits(self, client: TestClient) -> None:
        headers = _auth_headers(client)
        resp = _upload_csv(client, headers, SUMMARY_CSV)
        assert resp.status_code == 201
        body = resp.json()

        workout = body["workout"]
        assert workout["has_splits"] is False
        assert any("summary" in w.lower() for w in body["warnings"])

    def test_upload_requires_auth(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/workouts/upload",
            files={"file": ("workout.csv", io.BytesIO(DETAILED_CSV.encode()), "text/csv")},
        )
        assert resp.status_code == 401

    def test_upload_rejects_empty_file(self, client: TestClient) -> None:
        headers = _auth_headers(client)
        resp = client.post(
            "/api/v1/workouts/upload",
            headers=headers,
            files={"file": ("empty.csv", io.BytesIO(b""), "text/csv")},
        )
        assert resp.status_code == 400

    def test_upload_rejects_garbage_csv_with_useful_error(self, client: TestClient) -> None:
        headers = _auth_headers(client)
        resp = _upload_csv(client, headers, "foo,bar\n1,2\n")
        assert resp.status_code == 422
        assert "detail" in resp.json()


class TestManualEntry:
    def test_create_manual_workout(self, client: TestClient) -> None:
        headers = _auth_headers(client)
        resp = client.post(
            "/api/v1/workouts",
            headers=headers,
            json={
                "title": "Easy row",
                "date": "2026-08-10T09:00:00Z",
                "segments": [{"type": "work", "distance_m": 6000, "duration_s": 1500}],
            },
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["total_distance_m"] == 6000.0
        assert body["has_splits"] is False

    def test_manual_workout_requires_at_least_one_segment(self, client: TestClient) -> None:
        headers = _auth_headers(client)
        resp = client.post(
            "/api/v1/workouts",
            headers=headers,
            json={"title": "Bad entry", "date": "2026-08-10T09:00:00Z", "segments": []},
        )
        assert resp.status_code == 422


class TestListAndDetail:
    def test_list_workouts_returns_only_own_workouts(self, client: TestClient) -> None:
        headers_a = _auth_headers(client, email="a@example.com")
        headers_b = _auth_headers(client, email="b@example.com")
        _upload_csv(client, headers_a, DETAILED_CSV)

        resp_a = client.get("/api/v1/workouts", headers=headers_a)
        resp_b = client.get("/api/v1/workouts", headers=headers_b)

        assert resp_a.json()["total"] == 1
        assert resp_b.json()["total"] == 0

    def test_list_pagination(self, client: TestClient) -> None:
        headers = _auth_headers(client)
        for _ in range(3):
            _upload_csv(client, headers, DETAILED_CSV)

        resp = client.get("/api/v1/workouts?page=1&page_size=2", headers=headers)
        body = resp.json()
        assert body["total"] == 3
        assert len(body["items"]) == 2
        assert body["page"] == 1

    def test_get_workout_detail(self, client: TestClient) -> None:
        headers = _auth_headers(client)
        created = _upload_csv(client, headers, DETAILED_CSV).json()["workout"]

        resp = client.get(f"/api/v1/workouts/{created['id']}", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["id"] == created["id"]

    def test_cannot_access_another_users_workout(self, client: TestClient) -> None:
        headers_a = _auth_headers(client, email="a@example.com")
        headers_b = _auth_headers(client, email="b@example.com")
        created = _upload_csv(client, headers_a, DETAILED_CSV).json()["workout"]

        resp = client.get(f"/api/v1/workouts/{created['id']}", headers=headers_b)
        assert resp.status_code == 404

    def test_get_nonexistent_workout_404(self, client: TestClient) -> None:
        headers = _auth_headers(client)
        resp = client.get("/api/v1/workouts/999999", headers=headers)
        assert resp.status_code == 404


class TestDelete:
    def test_delete_own_workout(self, client: TestClient) -> None:
        headers = _auth_headers(client)
        created = _upload_csv(client, headers, DETAILED_CSV).json()["workout"]

        resp = client.delete(f"/api/v1/workouts/{created['id']}", headers=headers)
        assert resp.status_code == 204

        resp = client.get(f"/api/v1/workouts/{created['id']}", headers=headers)
        assert resp.status_code == 404

    def test_cannot_delete_another_users_workout(self, client: TestClient) -> None:
        headers_a = _auth_headers(client, email="a@example.com")
        headers_b = _auth_headers(client, email="b@example.com")
        created = _upload_csv(client, headers_a, DETAILED_CSV).json()["workout"]

        resp = client.delete(f"/api/v1/workouts/{created['id']}", headers=headers_b)
        assert resp.status_code == 404
