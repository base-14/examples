import pytest
from rest_framework import status


@pytest.mark.django_db
class TestRegister:
    def test_register_success(self, api_client):
        response = api_client.post(
            "/api/register",
            {"email": "new@example.com", "name": "New User", "password": "password123"},
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["user"]["email"] == "new@example.com"
        assert "access_token" in response.data["token"]

    def test_register_duplicate_email(self, api_client, user):
        response = api_client.post(
            "/api/register",
            {"email": user.email, "name": "Dup", "password": "password123"},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_register_missing_fields(self, api_client):
        response = api_client.post("/api/register", {}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_register_short_password(self, api_client):
        response = api_client.post(
            "/api/register",
            {"email": "short@example.com", "name": "Short", "password": "abc"},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
class TestLogin:
    def test_login_success(self, api_client, user):
        response = api_client.post(
            "/api/login",
            {"email": "test@example.com", "password": "testpassword123"},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["user"]["email"] == "test@example.com"
        assert "access_token" in response.data["token"]

    def test_login_wrong_password(self, api_client, user):
        response = api_client.post(
            "/api/login",
            {"email": user.email, "password": "wrongpassword"},
            format="json",
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_login_nonexistent_user(self, api_client):
        response = api_client.post(
            "/api/login",
            {"email": "nobody@example.com", "password": "password123"},
            format="json",
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
class TestGetUser:
    def test_get_user_authenticated(self, auth_client, user):
        response = auth_client.get("/api/user")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["email"] == user.email

    def test_get_user_unauthenticated(self, api_client):
        response = api_client.get("/api/user")
        assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
class TestLogout:
    def test_logout(self, auth_client):
        response = auth_client.post("/api/logout")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["message"] == "Logged out successfully"

    def test_logout_unauthenticated(self, api_client):
        response = api_client.post("/api/logout")
        assert response.status_code == status.HTTP_403_FORBIDDEN
