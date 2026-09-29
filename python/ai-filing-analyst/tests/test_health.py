import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.api_support import NoFramework, Rig


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> TestClient:
    monkeypatch.setenv("SEC_USER_AGENT", "Example Co ops@example.com")
    monkeypatch.setenv("FIXTURES_DIR", str(tmp_path))
    return TestClient(Rig(framework=NoFramework(), fixtures_dir=tmp_path).app())


def test_health_reports_fact_count_and_fixture_date(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "MANIFEST.json").write_text(json.dumps({"fetched": "2026-09-26"}))
    monkeypatch.setattr("filing_analyst.health.count_facts", lambda _dsn: 0)
    with client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "facts": 0,
        "fixture_date": "2026-09-26",
        "framework": "strands",
    }


def test_health_without_a_manifest_reports_no_fixture_date(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("filing_analyst.health.count_facts", lambda _dsn: 12)
    with client:
        body = client.get("/health").json()
    assert body["fixture_date"] is None
    assert body["facts"] == 12


def test_health_is_503_when_postgres_is_down(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def down(dsn: str) -> int:
        raise OSError("connection refused")

    monkeypatch.setattr("filing_analyst.health.count_facts", down)
    with client:
        response = client.get("/health")
    assert response.status_code == 503
    assert response.json()["status"] == "unavailable"


def test_app_refuses_to_start_without_a_user_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SEC_USER_AGENT", raising=False)
    from filing_analyst.config import SettingsError

    with pytest.raises(SettingsError), TestClient(Rig(framework=NoFramework()).app()):
        pass
