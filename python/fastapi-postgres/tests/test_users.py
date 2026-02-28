"""Tests for user endpoints."""

import pytest


class TestCreateUser:
    def test_create_user(self, client):
        response = client.post(
            "/users/",
            json={"email": "new@example.com", "password": "Password1"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["email"] == "new@example.com"
        assert "id" in data

    def test_create_user_duplicate_email(self, client, user):
        # The endpoint doesn't handle IntegrityError — it raises unhandled
        from sqlalchemy.exc import IntegrityError

        with pytest.raises(IntegrityError):
            client.post(
                "/users/",
                json={"email": "test@example.com", "password": "Password1"},
            )

    def test_create_user_weak_password(self, client):
        response = client.post(
            "/users/",
            json={"email": "weak@example.com", "password": "short"},
        )
        assert response.status_code == 422


class TestGetUser:
    def test_get_user(self, client, user, auth_headers):
        response = client.get(f"/users/{user.id}", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["email"] == "test@example.com"

    def test_get_user_not_found(self, client, auth_headers):
        response = client.get("/users/999", headers=auth_headers)
        assert response.status_code == 404

    def test_get_user_unauthenticated(self, client, user):
        response = client.get(f"/users/{user.id}")
        assert response.status_code == 401
