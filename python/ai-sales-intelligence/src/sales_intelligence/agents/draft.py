"""Draft agent - generates personalized outreach emails."""

import json
import logging
import re

from opentelemetry import trace

from sales_intelligence.llm import get_llm_client
from sales_intelligence.prompts import format_prompt
from sales_intelligence.state import AgentState, EmailDraft


logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


def strip_markdown_json(text: str) -> str:
    """Strip markdown code blocks from LLM response."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


async def draft_agent(state: AgentState) -> AgentState:
    """Generate personalized email drafts for scored prospects.

    Args:
        state: Current pipeline state with scored prospects

    Returns:
        Updated state with email drafts
    """
    with tracer.start_as_current_span("agent.draft") as span:
        span.set_attribute("campaign_id", state.campaign_id)
        span.set_attribute("scored_count", len(state.scored))

        if not state.scored:
            logger.info("No scored prospects for drafting")
            return state.model_copy(update={"current_step": "evaluate"})

        llm = get_llm_client()
        drafts: list[EmailDraft] = []
        errors: list[str] = list(state.errors)

        for scored in state.scored:
            with tracer.start_as_current_span("draft.email") as dspan:
                dspan.set_attribute("prospect_id", scored.prospect.connection_id)
                dspan.set_attribute("icp_score", scored.icp_score)

                system_prompt = format_prompt("draft", "system")
                user_prompt = format_prompt(
                    "draft",
                    "user",
                    first_name=scored.prospect.first_name,
                    last_name=scored.prospect.last_name,
                    company=scored.prospect.company,
                    position=scored.prospect.position,
                    industry=scored.enrichment.industry,
                    company_size=scored.enrichment.company_size,
                    pain_points=", ".join(scored.enrichment.pain_points),
                    recent_news=scored.enrichment.recent_news or "N/A",
                    icp_score=scored.icp_score,
                    score_reasoning=scored.reasoning,
                )

                try:
                    response = await llm.generate(
                        prompt=user_prompt,
                        system=system_prompt,
                        agent_name="draft",
                        campaign_id=state.campaign_id,
                    )
                    data = json.loads(strip_markdown_json(response))
                    drafts.append(
                        EmailDraft(
                            prospect_id=scored.prospect.connection_id,
                            subject=data.get("subject", ""),
                            body=data.get("body", ""),
                        )
                    )
                except json.JSONDecodeError as e:
                    logger.warning("Failed to parse draft for %s: %s", scored.prospect.company, e)
                    errors.append(f"Draft parse error for {scored.prospect.connection_id}: {e}")
                except Exception as e:
                    logger.error("Draft failed for %s: %s", scored.prospect.company, e)
                    errors.append(f"Draft error for {scored.prospect.connection_id}: {e}")

        span.set_attribute("drafts_count", len(drafts))
        logger.info("Generated %d email drafts", len(drafts))

        return state.model_copy(
            update={
                "drafts": drafts,
                "errors": errors,
                "current_step": "evaluate",
            }
        )
