"""Evaluate agent - quality checks email drafts.

CUSTOM instrumentation is required here because:
1. Auto-instrumentation doesn't capture evaluation semantics
2. OTel GenAI semconv defines gen_ai.evaluation.result events for quality tracking
3. Evaluation metrics enable quality dashboards and alerts
"""

import json
import logging
import re

from opentelemetry import metrics, trace

from sales_intelligence.llm import get_llm_client
from sales_intelligence.prompts import format_prompt
from sales_intelligence.state import AgentState, EvaluationResult


logger = logging.getLogger(__name__)
tracer = trace.get_tracer("gen_ai.evaluation")
meter = metrics.get_meter("gen_ai.evaluation")


def strip_markdown_json(text: str) -> str:
    """Strip markdown code blocks from LLM response."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


# Evaluation score histogram per OTel GenAI semconv
# Custom metric - enables quality trend dashboards
_evaluation_score = meter.create_histogram(
    name="gen_ai.evaluation.score",
    description="Quality evaluation scores (0-1 normalized)",
    unit="1",
)


async def evaluate_agent(state: AgentState) -> AgentState:
    """Evaluate email drafts for quality.

    Args:
        state: Current pipeline state with email drafts

    Returns:
        Updated state with evaluation results
    """
    with tracer.start_as_current_span("agent.evaluate") as span:
        span.set_attribute("campaign_id", state.campaign_id)
        span.set_attribute("drafts_count", len(state.drafts))
        span.set_attribute("quality_threshold", state.quality_threshold)

        if not state.drafts:
            logger.info("No drafts to evaluate")
            return state.model_copy(update={"current_step": "complete"})

        llm = get_llm_client()
        evaluations: list[EvaluationResult] = []
        errors: list[str] = list(state.errors)

        for draft in state.drafts:
            with tracer.start_as_current_span("evaluate.draft") as espan:
                espan.set_attribute("prospect_id", draft.prospect_id)

                system_prompt = format_prompt("evaluate", "system")
                user_prompt = format_prompt(
                    "evaluate",
                    "user",
                    subject=draft.subject,
                    body=draft.body,
                )

                try:
                    response = await llm.generate(
                        prompt=user_prompt,
                        system=system_prompt,
                        model=llm.model_fast,
                        agent_name="evaluate",
                        campaign_id=state.campaign_id,
                    )
                    data = json.loads(strip_markdown_json(response))
                    score = data.get("quality_score", 0)
                    passed = score >= state.quality_threshold

                    espan.set_attribute("quality_score", score)
                    espan.set_attribute("passed", passed)

                    # === OTel GenAI Evaluation Event ===
                    # CUSTOM EVENT: Per OTel GenAI semconv for evaluation results
                    # This enables evaluation tracking in Scout dashboards
                    # See: https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-events/
                    espan.add_event(
                        "gen_ai.evaluation.result",
                        attributes={
                            "gen_ai.evaluation.name": "email_quality",
                            "gen_ai.evaluation.score.value": score,
                            "gen_ai.evaluation.score.label": "passed" if passed else "failed",
                            "gen_ai.evaluation.explanation": data.get("feedback", "")[:200],
                        },
                    )

                    # Record evaluation metric for dashboards
                    _evaluation_score.record(
                        score / 100.0,
                        {
                            "gen_ai.evaluation.name": "email_quality",
                            "gen_ai.evaluation.score.label": "passed" if passed else "failed",
                            "campaign_id": state.campaign_id,
                        },
                    )

                    evaluations.append(
                        EvaluationResult(
                            draft_id=draft.prospect_id,
                            quality_score=score,
                            passed=passed,
                            feedback=data.get("feedback", ""),
                            issues=data.get("issues", []),
                        )
                    )
                except json.JSONDecodeError as e:
                    logger.warning("Failed to parse evaluation: %s", e)
                    errors.append(f"Evaluate parse error for {draft.prospect_id}: {e}")
                except Exception as e:
                    logger.error("Evaluation failed: %s", e)
                    errors.append(f"Evaluate error for {draft.prospect_id}: {e}")

        passed_count = sum(1 for e in evaluations if e.passed)
        span.set_attribute("evaluations_count", len(evaluations))
        span.set_attribute("passed_count", passed_count)
        logger.info(
            "Evaluated %d drafts, %d passed quality threshold", len(evaluations), passed_count
        )

        return state.model_copy(
            update={
                "evaluations": evaluations,
                "errors": errors,
                "current_step": "complete",
            }
        )
