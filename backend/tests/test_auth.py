from fastapi.testclient import TestClient

VALID_PASSWORD = "correct-horse-battery-staple"


def _register(client: TestClient, email: str = "athlete@example.com", password: str = VALID_PASSWORD):
    return client.post("/api/v1/auth/register", json={"email": email, "password": password})


class TestRegister:
    def test_register_creates_user_and_default_athlete(self, client: TestClient) -> None:
        resp = _register(client)
        assert resp.status_code == 201
        body = resp.json()

        assert body["user"]["email"] == "athlete@example.com"
        assert "id" in body["user"]
        assert body["access_token"]
        assert body["token_type"] == "bearer"

        # Signup must auto-create AND auto-select a default athlete -
        # the user should never see an empty athlete-selection screen.
        assert body["athlete"]["id"] is not None
        assert body["athlete"]["user_id"] == body["user"]["id"]
        assert body["athlete"]["name"]  # derived from email, non-empty

    def test_register_rejects_duplicate_email(self, client: TestClient) -> None:
        _register(client)
        resp = _register(client)
        assert resp.status_code == 409

    def test_register_rejects_short_password(self, client: TestClient) -> None:
        resp = _register(client, password="short")
        assert resp.status_code == 422

    def test_register_rejects_invalid_email(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/auth/register", json={"email": "not-an-email", "password": VALID_PASSWORD}
        )
        assert resp.status_code == 422


class TestLogin:
    def test_login_succeeds_with_correct_credentials(self, client: TestClient) -> None:
        _register(client)
        resp = client.post(
            "/api/v1/auth/login",
            json={"email": "athlete@example.com", "password": VALID_PASSWORD},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["access_token"]
        assert body["athlete"]["user_id"] == body["user"]["id"]

    def test_login_fails_with_wrong_password(self, client: TestClient) -> None:
        _register(client)
        resp = client.post(
            "/api/v1/auth/login",
            json={"email": "athlete@example.com", "password": "wrong-password"},
        )
        assert resp.status_code == 401

    def test_login_fails_for_unknown_email(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/auth/login",
            json={"email": "nobody@example.com", "password": VALID_PASSWORD},
        )
        assert resp.status_code == 401


class TestProtectedRoutes:
    def test_me_requires_auth(self, client: TestClient) -> None:
        resp = client.get("/api/v1/auth/me")
        assert resp.status_code == 401

    def test_me_returns_current_user_with_valid_token(self, client: TestClient) -> None:
        token = _register(client).json()["access_token"]
        resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json()["email"] == "athlete@example.com"

    def test_me_rejects_garbage_token(self, client: TestClient) -> None:
        resp = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
        assert resp.status_code == 401


class TestAthleteScoping:
    def test_list_athletes_returns_only_own_athlete(self, client: TestClient) -> None:
        body = _register(client, email="a@example.com").json()
        token = body["access_token"]
        user_id = body["user"]["id"]

        resp = client.get("/api/v1/athletes", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        athletes = resp.json()
        assert len(athletes) == 1
        assert athletes[0]["user_id"] == user_id

    def test_cannot_access_another_users_athlete(self, client: TestClient) -> None:
        body_a = _register(client, email="a@example.com").json()
        token_b = _register(client, email="b@example.com").json()["access_token"]

        other_athlete_id = body_a["athlete"]["id"]
        resp = client.get(
            f"/api/v1/athletes/{other_athlete_id}",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert resp.status_code == 404

    def test_update_own_athlete_profile(self, client: TestClient) -> None:
        body = _register(client).json()
        token = body["access_token"]
        athlete_id = body["athlete"]["id"]

        resp = client.patch(
            f"/api/v1/athletes/{athlete_id}",
            json={"weight_kg": 78.5, "training_level": "advanced"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        updated = resp.json()
        assert updated["weight_kg"] == 78.5
        assert updated["training_level"] == "advanced"
