"""Research agent - finds prospects matching campaign criteria."""

import logging

from opentelemetry import trace
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from sales_intelligence.models import Connection
from sales_intelligence.state import AgentState, ProspectData


logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


async def research_agent(state: AgentState, session: AsyncSession) -> AgentState:
    """Find connections matching target keywords and titles.

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

        filters = []
        for keyword in state.target_keywords:
            filters.append(Connection.company.ilike(f"%{keyword}%"))
            filters.append(Connection.position.ilike(f"%{keyword}%"))

        for title in state.target_titles:
            filters.append(Connection.position.ilike(f"%{title}%"))

        if not filters:
            logger.warning("No targeting criteria provided")
            return state.model_copy(update={"current_step": "enrich"})

        query = select(Connection).where(or_(*filters)).limit(50)
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
