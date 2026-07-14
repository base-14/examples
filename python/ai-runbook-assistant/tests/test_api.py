from fastapi.testclient import TestClient


def test_diagnose_returns_answer_and_id(monkeypatch):
    from runbook_assistant import main

    monkeypatch.setattr(main, "run_diagnosis", lambda *_a, **_k: "Check the disk-pressure runbook.")

    async def _fake_save(*_a, **_k):
        return "diag-123"

    monkeypatch.setattr(main, "save_diagnosis", _fake_save)

    app = main.create_app()
    app.state.agent = object()
    app.state.session_factory = None
    app.state.handler_factory = lambda _conversation_id: []

    client = TestClient(app)
    r = client.post("/api/v1/diagnose", json={"question": "node disk full?"})
    assert r.status_code == 200
    body = r.json()
    assert "disk" in body["answer"].lower()
    assert body["diagnosis_id"] == "diag-123"


def test_healthz():
    from runbook_assistant import main

    client = TestClient(main.create_app())
    assert client.get("/healthz").status_code == 200
