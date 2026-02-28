"""Tests for authentication endpoints."""


class TestRegister:
    def test_register_success(self, client, db):
        response = client.post(
            "/api/register",
            json={"email": "new@example.com", "name": "New User", "password": "password123"},
        )
        assert response.status_code == 201
        data = response.get_json()
        assert data["user"]["email"] == "new@example.com"
        assert "access_token" in data["token"]

    def test_register_duplicate_email(self, client, user):
        response = client.post(
            "/api/register",
            json={"email": "test@example.com", "name": "Dup", "password": "password123"},
        )
        assert response.status_code == 409

    def test_register_missing_fields(self, client, db):
        response = client.post("/api/register", json={})
        assert response.status_code == 400

    def test_register_invalid_email(self, client, db):
        response = client.post(
            "/api/register",
            json={"email": "not-an-email", "name": "Bad", "password": "password123"},
        )
        assert response.status_code == 400


class TestLogin:
    def test_login_success(self, client, user):
        response = client.post(
            "/api/login",
            json={"email": "test@example.com", "password": "password123"},
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["user"]["email"] == "test@example.com"
        assert "access_token" in data["token"]

    def test_login_wrong_password(self, client, user):
        response = client.post(
            "/api/login",
            json={"email": "test@example.com", "password": "wrongpassword"},
        )
        assert response.status_code == 401

    def test_login_nonexistent_user(self, client, db):
        response = client.post(
            "/api/login",
            json={"email": "nobody@example.com", "password": "password123"},
        )
        assert response.status_code == 401


class TestGetUser:
    def test_get_user_authenticated(self, client, user, auth_headers):
        response = client.get("/api/user", headers=auth_headers)
        assert response.status_code == 200
        assert response.get_json()["email"] == user.email

    def test_get_user_unauthenticated(self, client, db):
        response = client.get("/api/user")
        assert response.status_code == 401


class TestLogout:
    def test_logout(self, client, auth_headers):
        response = client.post("/api/logout", headers=auth_headers)
        assert response.status_code == 200
        assert response.get_json()["message"] == "Logged out successfully"

    def test_logout_unauthenticated(self, client, db):
        response = client.post("/api/logout")
        assert response.status_code == 401
