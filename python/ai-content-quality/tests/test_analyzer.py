from unittest.mock import AsyncMock, MagicMock, create_autospec, patch

import pytest

from content_quality.models.responses import (
    ContentIssue,
    ImprovementSuggestion,
    ImproveResult,
    ReviewResult,
    ScoreBreakdown,
    ScoreResult,
)
from content_quality.services.analyzer import ContentAnalyzer
from content_quality.services.llm import LLMClient
from content_quality.services.prompts import PromptPair


MOCK_PROMPT = PromptPair(system="test system", user="test {content}")


@pytest.fixture
def mock_llm_client() -> MagicMock:
    return create_autospec(LLMClient, instance=True)


@pytest.fixture
def analyzer(mock_llm_client: MagicMock) -> ContentAnalyzer:
    with (
        patch(
            "content_quality.services.analyzer.load_prompt",
            return_value=MOCK_PROMPT,
        ),
        patch("content_quality.services.analyzer.get_settings"),
    ):
        return ContentAnalyzer(mock_llm_client)


async def test_review_returns_review_result(
    analyzer: ContentAnalyzer, mock_llm_client: MagicMock
) -> None:
    mock_llm_client.generate_structured.return_value = ReviewResult(
        issues=[], summary="No issues", overall_quality="excellent"
    )
    result = await analyzer.review("Good content")
    assert isinstance(result, ReviewResult)
    assert result.overall_quality == "excellent"


async def test_review_passes_content_type(
    analyzer: ContentAnalyzer, mock_llm_client: MagicMock
) -> None:
    mock_llm_client.generate_structured.return_value = ReviewResult(
        issues=[], summary="Clean", overall_quality="good"
    )
    await analyzer.review("Content", content_type="technical")
    mock_llm_client.generate_structured.assert_called_once()
    call_kwargs = mock_llm_client.generate_structured.call_args
    assert call_kwargs.kwargs["content_type"] == "technical"
    assert call_kwargs.kwargs["endpoint"] == "/review"


async def test_review_passes_system_prompt(
    analyzer: ContentAnalyzer, mock_llm_client: MagicMock
) -> None:
    mock_llm_client.generate_structured.return_value = ReviewResult(
        issues=[], summary="OK", overall_quality="good"
    )
    await analyzer.review("Content")
    call_kwargs = mock_llm_client.generate_structured.call_args
    assert call_kwargs.kwargs["system_prompt"] == "test system"


async def test_improve_returns_improve_result(
    analyzer: ContentAnalyzer, mock_llm_client: MagicMock
) -> None:
    mock_llm_client.generate_structured.return_value = ImproveResult(
        suggestions=[ImprovementSuggestion(original="bad", improved="good", reason="clarity")],
        summary="One fix",
    )
    result = await analyzer.improve("Some content")
    assert isinstance(result, ImproveResult)
    assert len(result.suggestions) == 1


async def test_improve_passes_content_type(
    analyzer: ContentAnalyzer, mock_llm_client: MagicMock
) -> None:
    mock_llm_client.generate_structured.return_value = ImproveResult(
        suggestions=[], summary="Good"
    )
    await analyzer.improve("Content", content_type="marketing")
    call_kwargs = mock_llm_client.generate_structured.call_args
    assert call_kwargs.kwargs["content_type"] == "marketing"
    assert call_kwargs.kwargs["endpoint"] == "/improve"


async def test_score_returns_score_result(
    analyzer: ContentAnalyzer, mock_llm_client: MagicMock
) -> None:
    mock_llm_client.generate_structured.return_value = ScoreResult(
        score=75,
        breakdown=ScoreBreakdown(clarity=80, accuracy=70, engagement=75, originality=72),
        summary="Decent",
    )
    result = await analyzer.score("Content to score")
    assert isinstance(result, ScoreResult)
    assert result.score == 75


async def test_score_passes_endpoint(analyzer: ContentAnalyzer, mock_llm_client: MagicMock) -> None:
    mock_llm_client.generate_structured.return_value = ScoreResult(
        score=50,
        breakdown=ScoreBreakdown(clarity=50, accuracy=50, engagement=50, originality=50),
        summary="Average",
    )
    await analyzer.score("Content", content_type="blog")
    call_kwargs = mock_llm_client.generate_structured.call_args
    assert call_kwargs.kwargs["endpoint"] == "/score"
    assert call_kwargs.kwargs["content_type"] == "blog"


async def test_review_emits_evaluation_event(
    analyzer: ContentAnalyzer,
    mock_llm_client: MagicMock,
) -> None:
    mock_llm_client.generate_structured.return_value = ReviewResult(
        issues=[
            ContentIssue(type="hyperbole", description="Exaggerated", severity="high"),
            ContentIssue(type="grammar", description="Typo", severity="low"),
        ],
        summary="Issues found",
        overall_quality="fair",
    )

    with (
        patch("content_quality.services.analyzer.evaluation_score") as mock_eval_score,
        patch("content_quality.services.analyzer.trace") as mock_trace,
    ):
        mock_span = MagicMock()
        mock_trace.get_current_span.return_value = mock_span
        await analyzer.review("Test content")

    mock_span.add_event.assert_called_once()
    event_name, event_attrs = mock_span.add_event.call_args.args
    assert event_name == "gen_ai.evaluation.result"
    # high=30, low=10 -> 100-40=60
    assert event_attrs["gen_ai.evaluation.score.value"] == 60
    assert event_attrs["gen_ai.evaluation.score.label"] == "passed"

    mock_eval_score.record.assert_called_once_with(
        60, {"gen_ai.evaluation.name": "content_review", "content.type": "general"}
    )


async def test_score_emits_evaluation_event(
    analyzer: ContentAnalyzer,
    mock_llm_client: MagicMock,
) -> None:
    mock_llm_client.generate_structured.return_value = ScoreResult(
        score=45,
        breakdown=ScoreBreakdown(clarity=50, accuracy=40, engagement=45, originality=42),
        summary="Below average",
    )

    with (
        patch("content_quality.services.analyzer.evaluation_score") as mock_eval_score,
        patch("content_quality.services.analyzer.trace") as mock_trace,
    ):
        mock_span = MagicMock()
        mock_trace.get_current_span.return_value = mock_span
        await analyzer.score("Weak content", content_type="blog")

    event_name, event_attrs = mock_span.add_event.call_args.args
    assert event_name == "gen_ai.evaluation.result"
    assert event_attrs["gen_ai.evaluation.score.value"] == 45
    assert event_attrs["gen_ai.evaluation.score.label"] == "failed"

    mock_eval_score.record.assert_called_once_with(
        45, {"gen_ai.evaluation.name": "content_quality", "content.type": "blog"}
    )
