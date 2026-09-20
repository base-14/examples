"""Tests for the research agent."""

import uuid
from unittest.mock import AsyncMock, MagicMock

from opentelemetry.trace import SpanKind

from sales_intelligence.agents.research import DATA_SOURCE_ID, _build_websearch, research_agent
from sales_intelligence.state import AgentState


class TestBuildWebsearch:
    def test_single_keyword(self):
        assert _build_websearch(["AI"], []) == '"AI"'

    def test_multiple_keywords(self):
        result = _build_websearch(["SaaS", "Cloud"], [])
        assert result == '"SaaS" OR "Cloud"'

    def test_titles_only(self):
        result = _build_websearch([], ["CTO", "VP Engineering"])
        assert result == '"CTO" OR "VP Engineering"'

    def test_keywords_and_titles_combined(self):
        result = _build_websearch(["AI"], ["CTO"])
        assert result == '"AI" OR "CTO"'

    def test_empty_inputs(self):
        assert _build_websearch([], []) == ""

    def test_whitespace_terms_filtered(self):
        result = _build_websearch(["AI", "  ", ""], ["CTO"])
        assert result == '"AI" OR "CTO"'

    def test_multi_word_phrase_quoted(self):
        result = _build_websearch(["machine learning"], [])
        assert result == '"machine learning"'

    def test_strips_whitespace_from_terms(self):
        result = _build_websearch(["  AI  "], ["  CTO  "])
        assert result == '"AI" OR "CTO"'


class TestRetrievalSpan:
    async def test_fts_query_runs_inside_a_retrieval_span(self, span_exporter):
        session = MagicMock()
        session.execute = AsyncMock(return_value=MagicMock(scalars=lambda: MagicMock(all=list)))
        state = AgentState(
            campaign_id=str(uuid.uuid4()),
            target_keywords=["AI"],
            target_titles=["CTO"],
        )

        await research_agent(state, session)

        spans = {s.name: s for s in span_exporter.get_finished_spans()}
        retrieval = spans[f"retrieval {DATA_SOURCE_ID}"]
        assert retrieval.kind is SpanKind.CLIENT
        assert retrieval.attributes["gen_ai.operation.name"] == "retrieval"
        assert retrieval.attributes["gen_ai.data_source.id"] == DATA_SOURCE_ID
        assert retrieval.attributes["app.retrieval.chunk_count"] == 0
        assert retrieval.parent.span_id == spans["agent.research"].context.span_id
