import pytest
from pydantic import ValidationError

from content_quality.models.requests import ContentRequest
from content_quality.models.responses import (
    ContentIssue,
    ImprovementSuggestion,
    ImproveResult,
    ReviewResult,
    ScoreBreakdown,
    ScoreResult,
)


class TestContentRequest:
    def test_valid_request(self) -> None:
        req = ContentRequest(content="Hello world", content_type="blog")
        assert req.content == "Hello world"
        assert req.content_type == "blog"

    def test_default_content_type(self) -> None:
        req = ContentRequest(content="Hello world")
        assert req.content_type == "general"

    def test_empty_content_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ContentRequest(content="")

    def test_exceeds_max_length(self) -> None:
        with pytest.raises(ValidationError):
            ContentRequest(content="x" * 10_001)

    def test_at_max_length(self) -> None:
        req = ContentRequest(content="x" * 10_000)
        assert len(req.content) == 10_000

    def test_invalid_content_type(self) -> None:
        with pytest.raises(ValidationError):
            ContentRequest(content="Hello", content_type="invalid")  # type: ignore[arg-type]


class TestReviewResult:
    def test_review_with_issues(self) -> None:
        result = ReviewResult(
            issues=[
                ContentIssue(
                    type="grammar",
                    description="Missing comma",
                    severity="low",
                )
            ],
            summary="Minor grammar issue found",
            overall_quality="good",
        )
        assert len(result.issues) == 1
        assert result.issues[0].type == "grammar"

    def test_review_empty_issues(self) -> None:
        result = ReviewResult(
            issues=[],
            summary="No issues found",
            overall_quality="excellent",
        )
        assert result.issues == []

    def test_issue_with_location(self) -> None:
        issue = ContentIssue(
            type="bias",
            description="Loaded language",
            location="paragraph 2",
            severity="high",
        )
        assert issue.location == "paragraph 2"

    def test_issue_location_optional(self) -> None:
        issue = ContentIssue(
            type="unclear",
            description="Vague reference",
            severity="medium",
        )
        assert issue.location is None

    def test_issue_type_other(self) -> None:
        issue = ContentIssue(
            type="other",
            description="Uncategorized issue",
            severity="low",
        )
        assert issue.type == "other"

    def test_invalid_issue_type_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ContentIssue(
                type="nonexistent",  # type: ignore[arg-type]
                description="Bad type",
                severity="low",
            )


class TestImproveResult:
    def test_improve_with_suggestions(self) -> None:
        result = ImproveResult(
            suggestions=[
                ImprovementSuggestion(
                    original="This is very good",
                    improved="This is effective",
                    reason="Avoid vague qualifiers",
                )
            ],
            summary="One suggestion for clarity",
        )
        assert len(result.suggestions) == 1


class TestScoreResult:
    def test_valid_score(self) -> None:
        result = ScoreResult(
            score=85,
            breakdown=ScoreBreakdown(
                clarity=90,
                accuracy=80,
                engagement=85,
                originality=75,
            ),
            summary="Good quality content",
        )
        assert result.score == 85
        assert result.breakdown.clarity == 90

    def test_score_out_of_range(self) -> None:
        with pytest.raises(ValidationError):
            ScoreResult(
                score=101,
                breakdown=ScoreBreakdown(
                    clarity=90,
                    accuracy=80,
                    engagement=85,
                    originality=75,
                ),
                summary="Invalid",
            )

    def test_breakdown_out_of_range(self) -> None:
        with pytest.raises(ValidationError):
            ScoreBreakdown(
                clarity=-1,
                accuracy=80,
                engagement=85,
                originality=75,
            )
