"""Pytest fixtures for FastAPI application testing."""

import os

# Set env vars before importing anything from app
os.environ["OTEL_SDK_DISABLED"] = "true"
os.environ.setdefault("DB_HOSTNAME", "localhost")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("DB_NAME", "test")
os.environ.setdefault("DB_USERNAME", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("ALGORITHM", "HS256")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "30")

import datetime
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.oauth2 import create_access_token

# In-memory SQLite for tests
engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


@event.listens_for(engine, "connect")
def _register_sqlite_functions(dbapi_conn, connection_record):
    dbapi_conn.create_function("NOW", 0, lambda: datetime.datetime.now(datetime.UTC).isoformat())


TestSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestSession()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db():
    session = TestSession()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client():
    # Patch telemetry setup to no-op and override DB
    with (
        patch("app.main.setup_telemetry"),
        patch("app.main.FastAPIInstrumentor"),
        patch("app.main.RequestsInstrumentor"),
        patch("app.main.MetricsMiddleware", lambda app: app),
    ):
        from app.main import app

        app.dependency_overrides[get_db] = override_get_db
        yield TestClient(app)
        app.dependency_overrides.clear()


@pytest.fixture
def user(db):
    from app.models import User
    from app.utils import hash_password

    user = User(email="test@example.com", password=hash_password("Password1"))
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def auth_headers(user):
    token = create_access_token(data={"user_id": user.id})
    return {"Authorization": f"Bearer {token}"}
