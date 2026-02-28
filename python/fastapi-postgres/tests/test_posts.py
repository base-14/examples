"""Tests for post endpoints."""


class TestCreatePost:
    def test_create_post(self, client, auth_headers):
        response = client.post(
            "/posts/",
            json={"title": "Test Post", "content": "Test content", "published": True},
            headers=auth_headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "Test Post"

    def test_create_post_unauthenticated(self, client):
        response = client.post(
            "/posts/",
            json={"title": "Test", "content": "Content"},
        )
        assert response.status_code == 401


class TestGetPosts:
    def test_get_posts_empty(self, client, auth_headers):
        response = client.get("/posts/", headers=auth_headers)
        assert response.status_code == 200
        assert response.json() == []

    def test_get_posts(self, client, auth_headers):
        client.post(
            "/posts/",
            json={"title": "Post 1", "content": "Content 1"},
            headers=auth_headers,
        )
        response = client.get("/posts/", headers=auth_headers)
        assert response.status_code == 200
        assert len(response.json()) == 1


class TestGetPost:
    def test_get_post(self, client, auth_headers):
        create_resp = client.post(
            "/posts/",
            json={"title": "Test Post", "content": "Content"},
            headers=auth_headers,
        )
        post_id = create_resp.json()["id"]

        response = client.get(f"/posts/{post_id}", headers=auth_headers)
        assert response.status_code == 200

    def test_get_post_not_found(self, client, auth_headers):
        response = client.get("/posts/999", headers=auth_headers)
        assert response.status_code == 404


class TestUpdatePost:
    def test_update_own_post(self, client, auth_headers):
        create_resp = client.post(
            "/posts/",
            json={"title": "Original", "content": "Content"},
            headers=auth_headers,
        )
        post_id = create_resp.json()["id"]

        response = client.put(
            f"/posts/{post_id}",
            json={"title": "Updated", "content": "New content"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["title"] == "Updated"

    def test_update_post_not_found(self, client, auth_headers):
        response = client.put(
            "/posts/999",
            json={"title": "X", "content": "Y"},
            headers=auth_headers,
        )
        assert response.status_code == 404


class TestDeletePost:
    def test_delete_own_post(self, client, auth_headers):
        create_resp = client.post(
            "/posts/",
            json={"title": "Delete me", "content": "Content"},
            headers=auth_headers,
        )
        post_id = create_resp.json()["id"]

        response = client.delete(f"/posts/{post_id}", headers=auth_headers)
        assert response.status_code == 204

    def test_delete_post_not_found(self, client, auth_headers):
        response = client.delete("/posts/999", headers=auth_headers)
        assert response.status_code == 404
