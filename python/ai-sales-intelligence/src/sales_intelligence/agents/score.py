"""Score agent - evaluates prospects against ideal customer profile."""

import json
import logging
import re

from opentelemetry import trace

from sales_intelligence.llm import get_llm_client
from sales_intelligence.prompts import format_prompt
from sales_intelligence.state import AgentState, ScoredProspect


logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


def strip_markdown_json(text: str) -> str:
    """Strip markdown code blocks from LLM response."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


async def score_agent(state: AgentState) -> AgentState:
    """Score prospects against ICP criteria.

    Args:
        state: Current pipeline state with prospects and enrichment

    Returns:
        Updated state with scored prospects (filtered by threshold)
    """
    with tracer.start_as_current_span("agent.score") as span:
        span.set_attribute("campaign_id", state.campaign_id)
        span.set_attribute("prospects_count", len(state.prospects))
        span.set_attribute("score_threshold", state.score_threshold)

        if not state.prospects or not state.enriched:
            logger.info("No prospects to score")
            return state.model_copy(update={"current_step": "draft"})

        llm = get_llm_client()
        scored: list[ScoredProspect] = []
        errors: list[str] = list(state.errors)

        for prospect, enrichment in zip(state.prospects, state.enriched, strict=False):
            with tracer.start_as_current_span("score.prospect") as pspan:
                pspan.set_attribute("prospect_id", prospect.connection_id)

                system_prompt = format_prompt("score", "system")
                user_prompt = format_prompt(
                    "score",
                    "user",
                    target_keywords=", ".join(state.target_keywords),
                    target_titles=", ".join(state.target_titles),
                    first_name=prospect.first_name,
                    last_name=prospect.last_name,
                    company=prospect.company,
                    position=prospect.position,
                    industry=enrichment.industry,
                    company_size=enrichment.company_size,
                    pain_points=", ".join(enrichment.pain_points),
                )

                try:
                    response = await llm.generate(
                        prompt=user_prompt,
                        system=system_prompt,
                        model=llm.model_fast,
                        agent_name="score",
                        campaign_id=state.campaign_id,
                    )
                    data = json.loads(strip_markdown_json(response))
                    score = data.get("icp_score", 0)
                    reasoning = data.get("reasoning", "")

                    pspan.set_attribute("icp_score", score)

                    if score >= state.score_threshold:
                        scored.append(
                            ScoredProspect(
                                prospect=prospect,
                                enrichment=enrichment,
                                icp_score=score,
                                reasoning=reasoning,
                            )
                        )
                except json.JSONDecodeError as e:
                    logger.warning("Failed to parse score for %s: %s", prospect.company, e)
                    errors.append(f"Score parse error for {prospect.connection_id}: {e}")
                except Exception as e:
                    logger.error("Scoring failed for %s: %s", prospect.company, e)
                    errors.append(f"Score error for {prospect.connection_id}: {e}")

        span.set_attribute("scored_count", len(scored))
        span.set_attribute("passed_threshold", len(scored))
        logger.info("Scored %d prospects, %d passed threshold", len(state.prospects), len(scored))

        return state.model_copy(
            update={
                "scored": scored,
                "errors": errors,
                "current_step": "draft",
            }
        )
