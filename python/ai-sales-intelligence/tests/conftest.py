"""Pytest fixtures for AI Sales Intelligence tests."""

import os
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from sales_intelligence.database import Base


os.environ["OTEL_ENABLED"] = "false"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"


@pytest.fixture
async def async_engine():
    """Create async SQLite engine for testing."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def session(async_engine) -> AsyncGenerator[AsyncSession]:
    """Create async session for testing."""
    async_session = async_sessionmaker(
        async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with async_session() as session:
        yield session


@pytest.fixture
def mock_anthropic_response():
    """Mock Anthropic API response."""
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text='{"key": "value"}')]
    mock_response.usage = MagicMock(input_tokens=100, output_tokens=50)
    return mock_response


@pytest.fixture
def mock_llm_client(mock_anthropic_response):
    """Mock LLM client."""
    client = AsyncMock()
    client.generate = AsyncMock(return_value='{"industry": "tech", "company_size": "startup"}')
    return client
