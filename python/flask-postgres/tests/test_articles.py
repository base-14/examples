"""Tests for article endpoints."""

from unittest.mock import patch


def _create_article(client, auth_headers, title="Test Article", body="Test body"):
    with patch("app.jobs.tasks.send_article_notification"):
        return client.post(
            "/api/articles/",
            json={"title": title, "body": body, "description": "Desc"},
            headers=auth_headers,
        )


class TestListArticles:
    def test_list_articles_empty(self, client, db):
        response = client.get("/api/articles/")
        assert response.status_code == 200
        assert response.get_json()["total"] == 0

    def test_list_articles(self, client, db, auth_headers):
        _create_article(client, auth_headers)
        response = client.get("/api/articles/")
        data = response.get_json()
        assert data["total"] == 1
        assert data["articles"][0]["title"] == "Test Article"

    def test_list_articles_search(self, client, db, auth_headers):
        _create_article(client, auth_headers, title="Flask Guide")
        _create_article(client, auth_headers, title="Django Guide")

        response = client.get("/api/articles/?search=Flask")
        assert response.get_json()["total"] == 1


class TestCreateArticle:
    @patch("app.jobs.tasks.send_article_notification")
    def test_create_article(self, mock_notify, client, db, auth_headers):
        response = client.post(
            "/api/articles/",
            json={"title": "New Article", "body": "Content", "description": "Desc"},
            headers=auth_headers,
        )
        assert response.status_code == 201
        data = response.get_json()
        assert data["title"] == "New Article"
        assert "slug" in data
        mock_notify.delay.assert_called_once()

    def test_create_article_unauthenticated(self, client, db):
        response = client.post(
            "/api/articles/",
            json={"title": "New", "body": "Body"},
        )
        assert response.status_code == 401

    @patch("app.jobs.tasks.send_article_notification")
    def test_create_article_missing_fields(self, mock_notify, client, db, auth_headers):
        response = client.post("/api/articles/", json={}, headers=auth_headers)
        assert response.status_code == 400
        mock_notify.delay.assert_not_called()


class TestGetArticle:
    def test_get_article(self, client, db, auth_headers):
        create_resp = _create_article(client, auth_headers)
        slug = create_resp.get_json()["slug"]

        response = client.get(f"/api/articles/{slug}")
        assert response.status_code == 200
        assert response.get_json()["title"] == "Test Article"

    def test_get_article_not_found(self, client, db):
        response = client.get("/api/articles/nonexistent-slug")
        assert response.status_code == 404


class TestUpdateArticle:
    def test_update_own_article(self, client, db, auth_headers):
        create_resp = _create_article(client, auth_headers)
        slug = create_resp.get_json()["slug"]

        response = client.put(
            f"/api/articles/{slug}",
            json={"title": "Updated Title"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.get_json()["title"] == "Updated Title"

    def test_update_other_users_article(self, client, app, db, auth_headers):
        create_resp = _create_article(client, auth_headers)
        slug = create_resp.get_json()["slug"]

        from app.models import User
        from app.services.auth import generate_token

        other = User(email="other@example.com", name="Other")
        other.set_password("password123")
        db.session.add(other)
        db.session.commit()

        with app.app_context():
            other_token = generate_token(other)

        response = client.put(
            f"/api/articles/{slug}",
            json={"title": "Hijacked"},
            headers={"Authorization": f"Bearer {other_token}"},
        )
        assert response.status_code == 403


class TestDeleteArticle:
    def test_delete_own_article(self, client, db, auth_headers):
        create_resp = _create_article(client, auth_headers)
        slug = create_resp.get_json()["slug"]

        response = client.delete(f"/api/articles/{slug}", headers=auth_headers)
        assert response.status_code == 204

    def test_delete_not_found(self, client, db, auth_headers):
        response = client.delete("/api/articles/nonexistent", headers=auth_headers)
        assert response.status_code == 404


class TestFavoriteArticle:
    def test_favorite_article(self, client, db, auth_headers):
        create_resp = _create_article(client, auth_headers)
        slug = create_resp.get_json()["slug"]

        response = client.post(f"/api/articles/{slug}/favorite", headers=auth_headers)
        assert response.status_code == 200
        assert response.get_json()["favorites_count"] == 1

    def test_unfavorite_article(self, client, db, auth_headers):
        create_resp = _create_article(client, auth_headers)
        slug = create_resp.get_json()["slug"]

        client.post(f"/api/articles/{slug}/favorite", headers=auth_headers)
        response = client.delete(f"/api/articles/{slug}/favorite", headers=auth_headers)
        assert response.status_code == 200
        assert response.get_json()["favorites_count"] == 0

    def test_favorite_unauthenticated(self, client, db, auth_headers):
        create_resp = _create_article(client, auth_headers)
        slug = create_resp.get_json()["slug"]

        response = client.post(f"/api/articles/{slug}/favorite")
        assert response.status_code == 401
