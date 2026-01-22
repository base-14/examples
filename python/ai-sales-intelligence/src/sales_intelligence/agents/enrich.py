"""Enrich agent - gathers additional context about prospects using LLM."""

import json
import logging
import re

from opentelemetry import trace

from sales_intelligence.llm import get_llm_client
from sales_intelligence.prompts import format_prompt
from sales_intelligence.state import AgentState, EnrichedData


logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


def strip_markdown_json(text: str) -> str:
    """Strip markdown code blocks from LLM response."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


async def enrich_agent(state: AgentState) -> AgentState:
    """Enrich prospects with company and role context.

    Args:
        state: Current pipeline state with prospects

    Returns:
        Updated state with enrichment data
    """
    with tracer.start_as_current_span("agent.enrich") as span:
        span.set_attribute("campaign_id", state.campaign_id)
        span.set_attribute("prospects_count", len(state.prospects))

        if not state.prospects:
            logger.info("No prospects to enrich")
            return state.model_copy(update={"current_step": "score"})

        llm = get_llm_client()
        enriched: list[EnrichedData] = []
        errors: list[str] = list(state.errors)

        for prospect in state.prospects:
            with tracer.start_as_current_span("enrich.prospect") as pspan:
                pspan.set_attribute("prospect_id", prospect.connection_id)
                pspan.set_attribute("company", prospect.company)

                system_prompt = format_prompt("enrich", "system")
                user_prompt = format_prompt(
                    "enrich",
                    "user",
                    company=prospect.company,
                    position=prospect.position,
                    first_name=prospect.first_name,
                    last_name=prospect.last_name,
                )

                try:
                    response = await llm.generate(
                        prompt=user_prompt,
                        system=system_prompt,
                        agent_name="enrich",
                        campaign_id=state.campaign_id,
                    )
                    data = json.loads(strip_markdown_json(response))
                    enriched.append(EnrichedData(**data))
                except json.JSONDecodeError as e:
                    logger.warning("Failed to parse enrichment for %s: %s", prospect.company, e)
                    enriched.append(EnrichedData(confidence=0.0))
                    errors.append(f"Enrich parse error for {prospect.connection_id}: {e}")
                except Exception as e:
                    logger.error("Enrichment failed for %s: %s", prospect.company, e)
                    enriched.append(EnrichedData(confidence=0.0))
                    errors.append(f"Enrich error for {prospect.connection_id}: {e}")

        span.set_attribute("enriched_count", len(enriched))

        return state.model_copy(
            update={
                "enriched": enriched,
                "errors": errors,
                "current_step": "score",
            }
        )
