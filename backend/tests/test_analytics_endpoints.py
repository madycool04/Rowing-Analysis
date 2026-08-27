import io

from fastapi.testclient import TestClient

VALID_PASSWORD = "correct-horse-battery-staple"

DETAILED_2K_CSV = """Date,Time,Distance,Pace,SPM,HR
2026-08-01,1:47.0,500,1:47.0,28,158
2026-08-01,1:46.2,500,1:46.2,29,164
2026-08-01,1:44.8,500,1:44.8,30,170
2026-08-01,1:42.5,500,1:42.5,32,178
"""


def _auth_headers(client: TestClient, email: str = "rower@example.com") -> dict[str, str]:
    resp = client.post("/api/v1/auth/register", json={"email": email, "password": VALID_PASSWORD})
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _upload(client: TestClient, headers: dict[str, str], content: str = DETAILED_2K_CSV):
    return client.post(
        "/api/v1/workouts/upload",
        headers=headers,
        files={"file": ("workout.csv", io.BytesIO(content.encode()), "text/csv")},
    )


class TestPerformanceEndpoint:
    def test_requires_auth(self, client: TestClient) -> None:
        resp = client.get("/api/v1/analytics/performance")
        assert resp.status_code == 401

    def test_returns_envelope_shape(self, client: TestClient) -> None:
        headers = _auth_headers(client)
        _upload(client, headers)
        resp = client.get("/api/v1/analytics/performance", headers=headers)
        assert resp.status_code == 200
        body = resp.json()
        assert "metrics" in body and "data_quality" in body and "insights" in body
        assert "personal_bests" in body["metrics"]
        assert "2k" in body["metrics"]["personal_bests"]

    def test_empty_history_returns_no_pbs(self, client: TestClient) -> None:
        headers = _auth_headers(client)
        resp = client.get("/api/v1/analytics/performance", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["metrics"]["personal_bests"] == {}


class TestTrainingLoadEndpoint:
    def test_requires_auth(self, client: TestClient) -> None:
        resp = client.get("/api/v1/analytics/training-load")
        assert resp.status_code == 401

    def test_returns_daily_series(self, client: TestClient) -> None:
        headers = _auth_headers(client)
        _upload(client, headers)
        resp = client.get("/api/v1/analytics/training-load", headers=headers)
        assert resp.status_code == 200
        body = resp.json()
        assert "daily_series" in body["metrics"]
        assert isinstance(body["metrics"]["daily_series"], list)

    def test_acwr_disclaimer_explicitly_denies_injury_prediction(self, client: TestClient) -> None:
        headers = _auth_headers(client)
        _upload(client, headers)
        resp = client.get("/api/v1/analytics/training-load", headers=headers)
        body = resp.json()
        # With a single workout, ACWR is always 4.0 (7-day and 28-day
        # windows both equal that one day's load), which crosses the
        # insight threshold - so this should reliably produce the
        # disclaimer rather than an unqualified claim.
        assert any("not an injury prediction" in insight.lower() for insight in body["insights"])
        assert not any(
            ("predicts" in insight.lower() and "injury" in insight.lower())
            for insight in body["insights"]
        )


class TestTrendsEndpoint:
    def test_requires_auth(self, client: TestClient) -> None:
        resp = client.get("/api/v1/analytics/trends")
        assert resp.status_code == 401

    def test_returns_all_expected_series_keys(self, client: TestClient) -> None:
        headers = _auth_headers(client)
        _upload(client, headers)
        resp = client.get("/api/v1/analytics/trends", headers=headers)
        assert resp.status_code == 200
        metrics = resp.json()["metrics"]
        for key in [
            "performance_2k",
            "performance_5k",
            "avg_watts",
            "avg_hr",
            "efficiency_factor",
            "training_load",
            "pacing_consistency",
            "interval_decay",
        ]:
            assert key in metrics

    def test_2k_workout_appears_in_2k_progression(self, client: TestClient) -> None:
        headers = _auth_headers(client)
        _upload(client, headers)
        resp = client.get("/api/v1/analytics/trends", headers=headers)
        assert len(resp.json()["metrics"]["performance_2k"]) == 1

    def test_date_range_filtering(self, client: TestClient) -> None:
        headers = _auth_headers(client)
        _upload(client, headers)
        resp = client.get(
            "/api/v1/analytics/trends?start_date=2099-01-01&end_date=2099-12-31",
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["metrics"]["avg_watts"] == []


class TestCrossUserIsolation:
    def test_trends_scoped_to_own_athlete(self, client: TestClient) -> None:
        headers_a = _auth_headers(client, email="a@example.com")
        headers_b = _auth_headers(client, email="b@example.com")
        _upload(client, headers_a)

        resp_a = client.get("/api/v1/analytics/trends", headers=headers_a)
        resp_b = client.get("/api/v1/analytics/trends", headers=headers_b)

        assert len(resp_a.json()["metrics"]["avg_watts"]) == 1
        assert len(resp_b.json()["metrics"]["avg_watts"]) == 0
