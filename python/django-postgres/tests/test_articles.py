from unittest.mock import patch

import pytest
from rest_framework import status


@pytest.mark.django_db
class TestListArticles:
    def test_list_articles(self, api_client, article):
        response = api_client.get("/api/articles/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 1
        assert response.data["articles"][0]["title"] == article.title

    def test_list_articles_empty(self, api_client):
        response = api_client.get("/api/articles/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 0

    def test_list_articles_search(self, api_client, article):
        response = api_client.get("/api/articles/", {"search": "Test"})
        assert response.data["count"] == 1

        response = api_client.get("/api/articles/", {"search": "nonexistent"})
        assert response.data["count"] == 0

    def test_list_articles_filter_by_author(self, api_client, article, user):
        response = api_client.get("/api/articles/", {"author": user.email})
        assert response.data["count"] == 1

        response = api_client.get("/api/articles/", {"author": "other@example.com"})
        assert response.data["count"] == 0


@pytest.mark.django_db
class TestCreateArticle:
    @patch("apps.articles.views.send_article_notification.delay")
    def test_create_article(self, mock_notify, auth_client):
        response = auth_client.post(
            "/api/articles/",
            {"title": "New Article", "body": "Some content", "description": "Desc"},
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["title"] == "New Article"
        assert response.data["slug"].startswith("new-article-")
        mock_notify.assert_called_once()

    def test_create_article_unauthenticated(self, api_client):
        response = api_client.post(
            "/api/articles/",
            {"title": "New", "body": "Body"},
            format="json",
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    @patch("apps.articles.views.send_article_notification.delay")
    def test_create_article_missing_fields(self, mock_notify, auth_client):
        response = auth_client.post("/api/articles/", {}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        mock_notify.assert_not_called()


@pytest.mark.django_db
class TestArticleDetail:
    def test_get_article(self, api_client, article):
        response = api_client.get(f"/api/articles/{article.slug}")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["title"] == article.title

    def test_get_article_not_found(self, api_client):
        response = api_client.get("/api/articles/nonexistent-slug")
        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
class TestUpdateArticle:
    def test_update_own_article(self, auth_client, article):
        response = auth_client.put(
            f"/api/articles/{article.slug}",
            {"title": "Updated Title"},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["title"] == "Updated Title"

    def test_update_other_users_article(self, api_client, article):
        from apps.users.authentication import generate_token
        from apps.users.models import User

        other = User.objects.create_user(
            email="other@example.com", password="password123", name="Other"
        )
        token = generate_token(other)
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        response = api_client.put(
            f"/api/articles/{article.slug}",
            {"title": "Hijacked"},
            format="json",
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
class TestDeleteArticle:
    def test_delete_own_article(self, auth_client, article):
        response = auth_client.delete(f"/api/articles/{article.slug}")
        assert response.status_code == status.HTTP_204_NO_CONTENT

    def test_delete_other_users_article(self, api_client, article):
        from apps.users.authentication import generate_token
        from apps.users.models import User

        other = User.objects.create_user(
            email="other@example.com", password="password123", name="Other"
        )
        token = generate_token(other)
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        response = api_client.delete(f"/api/articles/{article.slug}")
        assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
class TestFavoriteArticle:
    def test_favorite_article(self, auth_client, article):
        response = auth_client.post(f"/api/articles/{article.slug}/favorite")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["favorites_count"] == 1

    def test_unfavorite_article(self, auth_client, article):
        auth_client.post(f"/api/articles/{article.slug}/favorite")
        response = auth_client.delete(f"/api/articles/{article.slug}/favorite")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["favorites_count"] == 0

    def test_double_favorite(self, auth_client, article):
        auth_client.post(f"/api/articles/{article.slug}/favorite")
        response = auth_client.post(f"/api/articles/{article.slug}/favorite")
        assert response.status_code == status.HTTP_409_CONFLICT

    def test_favorite_unauthenticated(self, api_client, article):
        response = api_client.post(f"/api/articles/{article.slug}/favorite")
        assert response.status_code == status.HTTP_403_FORBIDDEN
