"""LangGraph pipeline for sales intelligence workflow.

Uses LangGraph StateGraph for agent orchestration with OTel tracing.
Auto-instrumentation is not available for agent orchestration - CUSTOM spans are
required to track agent execution, which enables:
- Pipeline performance analysis (which agent is the bottleneck?)
- Error attribution (which agent failed?)
- Cost attribution per agent
"""

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from langgraph.graph import END, START, StateGraph
from opentelemetry import trace
from sqlalchemy.ext.asyncio import AsyncSession

from sales_intelligence.agents.draft import draft_agent
from sales_intelligence.agents.enrich import enrich_agent
from sales_intelligence.agents.evaluate import evaluate_agent
from sales_intelligence.agents.research import research_agent
from sales_intelligence.agents.score import score_agent
from sales_intelligence.state import AgentState


logger = logging.getLogger(__name__)
tracer = trace.get_tracer("gen_ai.agent")


def create_pipeline(session: AsyncSession) -> Any:
    """Create the sales intelligence pipeline.

    Pipeline flow:
    START -> research -> enrich -> score -> draft -> evaluate -> END

    Args:
        session: Database session for research agent

    Returns:
        Compiled StateGraph
    """

    def wrap_agent(
        name: str, agent_fn: Callable[..., Awaitable[AgentState]], needs_session: bool = False
    ) -> Callable[[AgentState], Awaitable[AgentState]]:
        """Wrap agent function with OTel GenAI agent span convention.

        CUSTOM SPAN: OTel GenAI semantic conventions for agent invocation.
        This is required because there's no auto-instrumentation for LangGraph.
        Span naming follows: "invoke_agent {agent_name}" per GenAI semconv.
        """

        async def wrapped(state: AgentState) -> AgentState:
            # Agent span per OTel GenAI semantic conventions
            # See: https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-agent-spans/
            with tracer.start_as_current_span(f"invoke_agent {name}") as span:
                # === REQUIRED attributes for agent spans ===
                span.set_attribute("gen_ai.operation.name", "invoke_agent")
                span.set_attribute("gen_ai.agent.name", name)

                # === CUSTOM business context ===
                span.set_attribute("campaign_id", state.campaign_id)

                if needs_session:
                    result = await agent_fn(state, session)
                else:
                    result = await agent_fn(state)

                # Record outcome for debugging
                span.set_attribute("errors_count", len(result.errors))
                return result

        return wrapped

    graph: Any = StateGraph(AgentState)

    graph.add_node("research", wrap_agent("research", research_agent, needs_session=True))
    graph.add_node("enrich", wrap_agent("enrich", enrich_agent))
    graph.add_node("score", wrap_agent("score", score_agent))
    graph.add_node("draft", wrap_agent("draft", draft_agent))
    graph.add_node("evaluate", wrap_agent("evaluate", evaluate_agent))

    graph.add_edge(START, "research")
    graph.add_edge("research", "enrich")
    graph.add_edge("enrich", "score")
    graph.add_edge("score", "draft")
    graph.add_edge("draft", "evaluate")
    graph.add_edge("evaluate", END)

    return graph.compile()


async def run_pipeline(
    campaign_id: str,
    target_keywords: list[str],
    target_titles: list[str],
    session: AsyncSession,
    score_threshold: int = 50,
    quality_threshold: int = 60,
) -> AgentState:
    """Run the sales intelligence pipeline.

    Args:
        campaign_id: Campaign identifier
        target_keywords: Keywords to match (company, industry)
        target_titles: Job titles to target
        session: Database session
        score_threshold: Minimum ICP score (0-100)
        quality_threshold: Minimum email quality score (0-100)

    Returns:
        Final pipeline state with all results
    """
    with tracer.start_as_current_span("pipeline.run") as span:
        span.set_attribute("campaign_id", campaign_id)
        span.set_attribute("target_keywords", target_keywords)
        span.set_attribute("target_titles", target_titles)

        initial_state = AgentState(
            campaign_id=campaign_id,
            target_keywords=target_keywords,
            target_titles=target_titles,
            score_threshold=score_threshold,
            quality_threshold=quality_threshold,
        )

        pipeline = create_pipeline(session)
        result: Any = await pipeline.ainvoke(initial_state)

        final_state = AgentState(**result) if isinstance(result, dict) else result

        span.set_attribute("prospects_found", len(final_state.prospects))
        span.set_attribute("drafts_generated", len(final_state.drafts))
        span.set_attribute(
            "evaluations_passed", sum(1 for e in final_state.evaluations if e.passed)
        )
        span.set_attribute("errors_count", len(final_state.errors))

        logger.info(
            "Pipeline completed: %d prospects, %d drafts, %d passed evaluation",
            len(final_state.prospects),
            len(final_state.drafts),
            sum(1 for e in final_state.evaluations if e.passed),
        )

        return final_state
