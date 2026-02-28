"""Tests for task CRUD endpoints."""


class TestPing:
    def test_ping(self, client):
        response = client.get("/ping")
        assert response.status_code == 200
        assert response.json() == {"message": "pong"}


class TestCreateTask:
    def test_create_task(self, client):
        response = client.post("/tasks/", json={"title": "Test task"})
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Test task"
        assert data["status"] == "pending"
        assert "id" in data

    def test_create_task_no_title(self, client):
        response = client.post("/tasks/", json={})
        assert response.status_code == 422


class TestListTasks:
    def test_list_tasks_empty(self, client):
        response = client.get("/tasks/")
        assert response.status_code == 200
        assert response.json() == []

    def test_list_tasks(self, client):
        client.post("/tasks/", json={"title": "Task 1"})
        client.post("/tasks/", json={"title": "Task 2"})
        response = client.get("/tasks/")
        assert response.status_code == 200
        assert len(response.json()) == 2

    def test_list_tasks_pagination(self, client):
        for i in range(5):
            client.post("/tasks/", json={"title": f"Task {i}"})
        response = client.get("/tasks/?limit=2&skip=1")
        assert response.status_code == 200
        assert len(response.json()) == 2


class TestGetTask:
    def test_get_task(self, client):
        create_resp = client.post("/tasks/", json={"title": "Get me"})
        task_id = create_resp.json()["id"]

        response = client.get(f"/tasks/{task_id}")
        assert response.status_code == 200
        assert response.json()["title"] == "Get me"

    def test_get_task_not_found(self, client):
        response = client.get("/tasks/999")
        assert response.status_code == 404
