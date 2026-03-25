"""Tests for research agent helper functions."""

from sales_intelligence.agents.research import _build_websearch


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
