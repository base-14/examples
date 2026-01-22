"""Tests for FastAPI endpoints.

Uses testcontainers for PostgreSQL.
Run with: pytest -m integration
"""

import os
from collections.abc import AsyncGenerator
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer

from sales_intelligence.database import Base


os.environ["OTEL_ENABLED"] = "false"

pytestmark = pytest.mark.integration

_db_url = None
_schema_created = False


@pytest.fixture(scope="module")
def postgres_container():
    """Start PostgreSQL container."""
    global _db_url, _schema_created

    container = PostgresContainer(
        image="postgres:18",
        username="test",
        password="test",
        dbname="test_db",
    )
    container.start()

    host = container.get_container_host_ip()
    port = container.get_exposed_port(5432)
    _db_url = f"postgresql+asyncpg://test:test@{host}:{port}/test_db"
    _schema_created = False

    yield container

    container.stop()


@pytest.fixture
def client(postgres_container):
    """Create test client with fresh engine per test."""
    engine = create_async_engine(_db_url, echo=False)
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def create_schema_if_needed():
        global _schema_created
        if not _schema_created:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            _schema_created = True

    async def override_get_session() -> AsyncGenerator[AsyncSession]:
        await create_schema_if_needed()
        async with async_session() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def mock_init_db() -> None:
        await create_schema_if_needed()

    async def mock_close_db() -> None:
        pass

    with (
        patch("sales_intelligence.main.setup_telemetry") as mock_telemetry,
        patch("sales_intelligence.main.instrument_fastapi"),
        patch("sales_intelligence.main.init_db", mock_init_db),
        patch("sales_intelligence.main.close_db", mock_close_db),
    ):
        mock_telemetry.return_value = (None, None)
        from sales_intelligence.database import get_session
        from sales_intelligence.main import app

        app.dependency_overrides[get_session] = override_get_session

        with TestClient(app) as test_client:
            yield test_client

        app.dependency_overrides.clear()


class TestHealthEndpoint:
    def test_health_check(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "ai-sales-intelligence"
        assert data["version"] == "2.0.0"


class TestCampaignEndpoints:
    def test_create_campaign(self, client):
        response = client.post(
            "/campaigns",
            json={
                "name": "Test Campaign",
                "target_keywords": ["SaaS", "AI"],
                "target_titles": ["CTO", "VP Engineering"],
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Test Campaign"
        assert data["target_keywords"] == ["SaaS", "AI"]
        assert data["status"] == "draft"

    def test_get_campaign_not_found(self, client):
        response = client.get("/campaigns/00000000-0000-0000-0000-000000000000")
        assert response.status_code == 404

    def test_get_campaign_invalid_id(self, client):
        response = client.get("/campaigns/invalid-id")
        assert response.status_code == 400


class TestConnectionImport:
    def test_import_csv(self, client):
        csv_content = """First Name,Last Name,Email Address,Company,Position
John,Doe,john@example.com,Acme Inc,CTO
Jane,Smith,jane@example.com,Tech Corp,VP Engineering"""

        response = client.post(
            "/connections/import",
            files={"file": ("connections.csv", csv_content, "text/csv")},
        )
        assert response.status_code == 200
        assert response.json()["imported"] == 2

    def test_import_invalid_file(self, client):
        response = client.post(
            "/connections/import",
            files={"file": ("data.txt", "not csv", "text/plain")},
        )
        assert response.status_code == 400
