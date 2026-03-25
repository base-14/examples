"""Research agent - finds prospects matching campaign criteria.

Uses PostgreSQL full-text search (FTS) to match connections against
campaign target keywords and titles. GIN index on the tsvector column
makes this efficient even at scale.
"""

import logging
import uuid

from opentelemetry import trace
from sqlalchemy import func, literal_column, select
from sqlalchemy.ext.asyncio import AsyncSession

from sales_intelligence.models import Connection
from sales_intelligence.state import AgentState, ProspectData


logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

# Raw SQL expression matching the GIN index definition in models.py exactly,
# so PostgreSQL uses the index instead of a sequential scan.
_TSVECTOR_EXPR = literal_column(
    "to_tsvector('english', "
    "coalesce(first_name, '') || ' ' || coalesce(last_name, '') || ' ' "
    "|| coalesce(company, '') || ' ' || coalesce(position, ''))"
)


def _build_websearch(keywords: list[str], titles: list[str]) -> str:
    """Build a websearch_to_tsquery input string from keywords and titles.

    Uses quoted phrases for multi-word terms and OR between all terms.
    websearch_to_tsquery handles sanitization — no raw tsquery operators.
    """
    terms = []
    for term in keywords + titles:
        cleaned = term.strip()
        if cleaned:
            terms.append(f'"{cleaned}"')
    return " OR ".join(terms)


async def research_agent(state: AgentState, session: AsyncSession) -> AgentState:
    """Find connections matching target keywords and titles using FTS.

    Args:
        state: Current pipeline state with targeting criteria
        session: Database session

    Returns:
        Updated state with prospects list
    """
    with tracer.start_as_current_span("agent.research") as span:
        span.set_attribute("campaign_id", state.campaign_id)
        span.set_attribute("target_keywords", state.target_keywords)
        span.set_attribute("target_titles", state.target_titles)

        campaign_id = state.campaign_id

        if not state.target_keywords and not state.target_titles:
            logger.warning("No targeting criteria provided")
            return state.model_copy(update={"current_step": "enrich"})

        websearch_str = _build_websearch(state.target_keywords, state.target_titles)
        if not websearch_str:
            logger.warning("No valid search terms after filtering")
            return state.model_copy(update={"current_step": "enrich"})

        span.set_attribute("fts.query", websearch_str)

        tsquery = func.websearch_to_tsquery("english", websearch_str)

        query = (
            select(Connection)
            .where(Connection.campaign_id == uuid.UUID(campaign_id))
            .where(_TSVECTOR_EXPR.bool_op("@@")(tsquery))
            .order_by(func.ts_rank(_TSVECTOR_EXPR, tsquery).desc())
            .limit(50)
        )
        result = await session.execute(query)
        connections = result.scalars().all()

        prospects = [
            ProspectData(
                connection_id=str(c.id),
                first_name=c.first_name,
                last_name=c.last_name,
                company=c.company or "",
                position=c.position or "",
                email=c.email,
            )
            for c in connections
        ]

        span.set_attribute("prospects_found", len(prospects))
        logger.info("Found %d prospects", len(prospects))

        return state.model_copy(
            update={
                "prospects": prospects,
                "current_step": "enrich",
            }
        )
