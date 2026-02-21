from typing import TYPE_CHECKING, cast

from llama_index.core import PromptTemplate
from opentelemetry import metrics, trace

from content_quality.config import get_settings
from content_quality.models.responses import ImproveResult, ReviewResult, ScoreResult
from content_quality.services.prompts import load_prompt


if TYPE_CHECKING:
    from content_quality.services.llm import LLMClient


evaluation_score = metrics.get_meter("gen_ai.client").create_histogram(
    name="gen_ai.evaluation.score",
    description="Content quality evaluation score",
    unit="1",
)

QUALITY_ISSUE_WEIGHTS = {"high": 3, "medium": 2, "low": 1}


class ContentAnalyzer:
    def __init__(self, llm_client: LLMClient) -> None:
        self.llm_client = llm_client
        settings = get_settings()
        self._review_prompt = load_prompt(f"review_{settings.review_prompt_version}")
        self._improve_prompt = load_prompt(f"improve_{settings.improve_prompt_version}")
        self._score_prompt = load_prompt(f"score_{settings.score_prompt_version}")

    async def review(self, content: str, content_type: str = "general") -> ReviewResult:
        result = cast(
            "ReviewResult",
            await self.llm_client.generate_structured(
                PromptTemplate(self._review_prompt.user),
                ReviewResult,
                content,
                content_type=content_type,
                endpoint="/review",
                system_prompt=self._review_prompt.system,
            ),
        )

        span = trace.get_current_span()
        issue_score = max(
            0, 100 - sum(QUALITY_ISSUE_WEIGHTS.get(i.severity, 1) * 10 for i in result.issues)
        )
        span.add_event(
            "gen_ai.evaluation.result",
            {
                "gen_ai.evaluation.name": "content_review",
                "gen_ai.evaluation.score.value": issue_score,
                "gen_ai.evaluation.score.label": "passed" if issue_score >= 60 else "failed",
                "gen_ai.evaluation.explanation": result.summary,
            },
        )
        evaluation_score.record(
            issue_score,
            {
                "gen_ai.evaluation.name": "content_review",
                "content.type": content_type,
            },
        )

        return result

    async def improve(self, content: str, content_type: str = "general") -> ImproveResult:
        return cast(
            "ImproveResult",
            await self.llm_client.generate_structured(
                PromptTemplate(self._improve_prompt.user),
                ImproveResult,
                content,
                content_type=content_type,
                endpoint="/improve",
                system_prompt=self._improve_prompt.system,
            ),
        )

    async def score(self, content: str, content_type: str = "general") -> ScoreResult:
        result = cast(
            "ScoreResult",
            await self.llm_client.generate_structured(
                PromptTemplate(self._score_prompt.user),
                ScoreResult,
                content,
                content_type=content_type,
                endpoint="/score",
                system_prompt=self._score_prompt.system,
            ),
        )

        span = trace.get_current_span()
        span.add_event(
            "gen_ai.evaluation.result",
            {
                "gen_ai.evaluation.name": "content_quality",
                "gen_ai.evaluation.score.value": result.score,
                "gen_ai.evaluation.score.label": "passed" if result.score >= 60 else "failed",
                "gen_ai.evaluation.explanation": result.summary,
            },
        )
        evaluation_score.record(
            result.score,
            {
                "gen_ai.evaluation.name": "content_quality",
                "content.type": content_type,
            },
        )

        return result
