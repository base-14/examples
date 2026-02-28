import os

import django
import pytest

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
os.environ["OTEL_SDK_DISABLED"] = "true"


def pytest_configure():
    django.setup()


@pytest.fixture
def api_client():
    from rest_framework.test import APIClient

    return APIClient()


@pytest.fixture
def user(db):  # noqa: ARG001
    from apps.users.models import User

    return User.objects.create_user(
        email="test@example.com",
        password="testpassword123",
        name="Test User",
    )


@pytest.fixture
def auth_client(api_client, user):
    from apps.users.authentication import generate_token

    token = generate_token(user)
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return api_client


@pytest.fixture
def article(db, user):  # noqa: ARG001
    from apps.articles.models import Article

    return Article.objects.create(
        title="Test Article",
        body="Test body content",
        description="Test description",
        author=user,
    )
