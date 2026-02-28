"""Pytest fixtures for Flask application testing."""

import os

import pytest


# Disable OpenTelemetry for tests
os.environ["OTEL_SDK_DISABLED"] = "true"


@pytest.fixture
def app():
    """Create test application."""
    from app import create_app
    from app.config import TestConfig

    app = create_app(TestConfig)
    app.config["TESTING"] = True

    yield app


@pytest.fixture
def client(app):
    """Create test client."""
    return app.test_client()


@pytest.fixture
def db(app):
    """Create test database."""
    from app.extensions import db as _db

    with app.app_context():
        _db.create_all()
        yield _db
        _db.drop_all()


@pytest.fixture
def user(db):
    """Create test user."""
    from app.models import User

    user = User(
        email="test@example.com",
        name="Test User",
    )
    user.set_password("password123")
    db.session.add(user)
    db.session.commit()

    return user


@pytest.fixture
def auth_token(app, user):
    """Generate auth token for test user."""
    from app.services.auth import generate_token

    with app.app_context():
        return generate_token(user)


@pytest.fixture
def auth_headers(auth_token):
    """Create authorization headers with test token."""
    return {"Authorization": f"Bearer {auth_token}"}
