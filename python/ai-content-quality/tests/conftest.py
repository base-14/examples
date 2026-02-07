import os


os.environ["OTEL_SDK_DISABLED"] = "true"

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from content_quality.main import app
from content_quality.models.responses import (
    ContentIssue,
    ImprovementSuggestion,
    ImproveResult,
    ReviewResult,
    ScoreBreakdown,
    ScoreResult,
)


@pytest.fixture
def mock_analyzer() -> AsyncMock:
    analyzer = AsyncMock()
    analyzer.review.return_value = ReviewResult(
        issues=[
            ContentIssue(
                type="grammar",
                description="Missing comma after introductory phrase",
                location="sentence 1",
                severity="low",
            )
        ],
        summary="Minor grammar issue found",
        overall_quality="good",
    )
    analyzer.improve.return_value = ImproveResult(
        suggestions=[
            ImprovementSuggestion(
                original="This is very good",
                improved="This is effective",
                reason="Avoid vague qualifiers",
            )
        ],
        summary="One suggestion for clarity",
    )
    analyzer.score.return_value = ScoreResult(
        score=82,
        breakdown=ScoreBreakdown(clarity=85, accuracy=80, engagement=82, originality=78),
        summary="Good quality content overall",
    )
    return analyzer


@pytest.fixture
def client(mock_analyzer: AsyncMock) -> TestClient:
    app.state.analyzer = mock_analyzer
    return TestClient(app)
