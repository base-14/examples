"""Pytest fixtures for FastAPI + Celery application testing."""

import datetime
import os
import sys
from unittest.mock import MagicMock, patch

os.environ["OTEL_SDK_DISABLED"] = "true"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Create test engine BEFORE importing app modules
test_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


@event.listens_for(test_engine, "connect")
def _register_sqlite_functions(dbapi_conn, connection_record):
    dbapi_conn.create_function("NOW", 0, lambda: datetime.datetime.now(datetime.UTC).isoformat())


TestSession = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def override_get_db():
    db = TestSession()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def setup_db():
    # Patch database module before importing main
    from app import database

    original_engine = database.engine
    original_session = database.SessionLocal

    database.engine = test_engine
    database.SessionLocal = TestSession

    database.Base.metadata.create_all(bind=test_engine)
    yield
    database.Base.metadata.drop_all(bind=test_engine)

    database.engine = original_engine
    database.SessionLocal = original_session


@pytest.fixture
def db():
    session = TestSession()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(setup_db):
    # Patch telemetry and task processing
    mock_task = MagicMock()
    with (
        patch("app.telemetry.setup_telemetry"),
        patch("app.telemetry.init_telemetry"),
        patch("app.tasks.process_task", mock_task),
    ):
        # Force reimport with patched modules
        for mod_name in list(sys.modules.keys()):
            if mod_name.startswith("app.main"):
                del sys.modules[mod_name]

        from app.database import Base

        Base.metadata.create_all(bind=test_engine)

        # Also patch the tasks reference inside main module
        import app.main as main_mod
        from app.main import app, get_db

        main_mod.tasks = MagicMock()

        app.dependency_overrides[get_db] = override_get_db
        yield TestClient(app)
        app.dependency_overrides.clear()
