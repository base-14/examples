"""Tests for authentication endpoints."""


class TestLogin:
    def test_login_success(self, client, user):
        response = client.post(
            "/login",
            data={"username": "test@example.com", "password": "Password1"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    def test_login_wrong_password(self, client, user):
        response = client.post(
            "/login",
            data={"username": "test@example.com", "password": "WrongPass1"},
        )
        assert response.status_code == 403

    def test_login_nonexistent_user(self, client):
        response = client.post(
            "/login",
            data={"username": "nobody@example.com", "password": "Password1"},
        )
        assert response.status_code == 403
