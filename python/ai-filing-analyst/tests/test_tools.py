import inspect
import json
from datetime import date
from typing import get_args

import httpx
import pytest
from pydantic import ValidationError

from filing_analyst.answer import RatioName, RatioUsed
from filing_analyst.sec_client import SecUnavailable, sec_question_scope
from filing_analyst.tools import (
    MAX_ROWS,
    RATIOS,
    ToolContext,
    bound_tools,
    compute_ratio,
    fiscal_year_of,
    frame_values,
    query_facts,
)
from filing_analyst.verifier import ToolResultCollector
from tests.sec_support import FakeClock, RecordingHandler, sec_client
from tests.tools_support import (
    AIRBNB,
    GITLAB,
    MONDAY,
    RINGCENTRAL,
    TEST_FIXTURES,
    WORKIVA,
    MemoryFacts,
    fact,
)


FRAME = json.loads((TEST_FIXTURES / "frame_NetIncomeLoss_USD_CY2024.json").read_text())


@pytest.fixture(scope="module")
def facts() -> MemoryFacts:
    return MemoryFacts.of(WORKIVA, RINGCENTRAL, MONDAY)


class TestQueryFacts:
    def test_the_revenue_alias_spans_both_ringcentral_concepts(self, facts: MemoryFacts) -> None:
        result = query_facts(facts, RINGCENTRAL, "revenue", 2011, 2017)
        by_year = {row["fiscal_year"]: row["concept"] for row in result["rows"]}
        assert sorted(by_year) == list(range(2011, 2018))
        assert {by_year[y] for y in range(2011, 2016)} == {"SalesRevenueNet"}
        assert (
            by_year[2016]
            == by_year[2017]
            == ("RevenueFromContractWithCustomerExcludingAssessedTax")
        )

    def test_only_annual_10k_rows_are_served(self, facts: MemoryFacts) -> None:
        rows = query_facts(facts, WORKIVA, "net_income")["rows"]
        assert {row["form"] for row in rows} <= {"10-K", "10-K/A"}
        for row in rows:
            days = (
                date.fromisoformat(row["period_end"]) - date.fromisoformat(row["period_start"])
            ).days
            assert 330 <= days <= 400

    def test_the_latest_filed_value_wins_for_a_revised_year(self, facts: MemoryFacts) -> None:
        (row,) = query_facts(facts, WORKIVA, "net_income", 2019, 2019)["rows"]
        assert row["value"] == -47479000
        assert row["accession"] == "0001445305-22-000041"

    def test_the_fiscal_year_comes_from_the_period_end(self, facts: MemoryFacts) -> None:
        (row,) = query_facts(facts, WORKIVA, "net_income", 2021, 2021)["rows"]
        assert row["fiscal_year"] == 2021
        assert row["period_end"] == "2021-12-31"
        assert row["accession"] == "0001445305-24-000021"

    def test_an_instant_has_no_start(self, facts: MemoryFacts) -> None:
        (row,) = query_facts(facts, WORKIVA, "total_assets", 2022, 2022)["rows"]
        assert row["period_start"] is None
        assert row["period_end"] == "2022-12-31"

    def test_per_share_figures_keep_their_unit(self, facts: MemoryFacts) -> None:
        rows = query_facts(facts, WORKIVA, "eps_basic")["rows"]
        assert rows
        assert {row["unit"] for row in rows} == {"USD/shares"}

    def test_rows_are_capped_at_twelve_newest_first(self, facts: MemoryFacts) -> None:
        result = query_facts(facts, RINGCENTRAL, "revenue")
        years = [row["fiscal_year"] for row in result["rows"]]
        assert len(years) == MAX_ROWS
        assert years == sorted(years, reverse=True)
        assert result["total_rows"] > MAX_ROWS
        assert "note" in result

    def test_a_20f_filer_returns_no_rows_and_no_error(self, facts: MemoryFacts) -> None:
        result = query_facts(facts, MONDAY, "revenue")
        assert result["rows"] == []
        assert "error" not in result
        assert "10-K" in result["note"]

    def test_an_amendment_wins_under_the_latest_filed_rule(self) -> None:
        start, end = date(2024, 1, 1), date(2024, 12, 31)
        reader = MemoryFacts(
            {
                1: [
                    fact(
                        "NetIncomeLoss",
                        100,
                        start=start,
                        end=end,
                        filed=date(2025, 2, 20),
                        accession="a-1",
                    ),
                    fact(
                        "NetIncomeLoss",
                        90,
                        start=start,
                        end=end,
                        form="10-K/A",
                        filed=date(2025, 5, 1),
                        accession="a-2",
                    ),
                    fact(
                        "NetIncomeLoss",
                        80,
                        start=start,
                        end=end,
                        form="10-Q",
                        filed=date(2025, 8, 1),
                        accession="a-3",
                    ),
                ]
            }
        )
        (row,) = query_facts(reader, 1, "net_income")["rows"]
        assert (row["value"], row["form"], row["accession"]) == (90, "10-K/A", "a-2")

    @pytest.mark.parametrize(
        "concept", ["revenue; DROP TABLE facts", "net income", "", "x" * 200, "Revenue'--"]
    )
    def test_a_concept_outside_the_pattern_is_an_error(
        self, facts: MemoryFacts, concept: str
    ) -> None:
        assert query_facts(facts, WORKIVA, concept)["error"] == "invalid_concept"

    @pytest.mark.parametrize(("start", "end"), [(1990, 2020), (2020, 2999), (2024, 2020)])
    def test_a_year_outside_the_range_is_an_error(
        self, facts: MemoryFacts, start: int, end: int
    ) -> None:
        assert query_facts(facts, WORKIVA, "revenue", start, end)["error"] == "invalid_year"

    def test_a_concept_the_company_never_reported_returns_no_rows(self, facts: MemoryFacts) -> None:
        result = query_facts(facts, WORKIVA, "HeadcountByRegion")
        assert result["rows"] == []
        assert "HeadcountByRegion" in result["note"]


@pytest.mark.parametrize(
    ("end", "year"),
    [(date(2024, 12, 31), 2024), (date(2025, 1, 31), 2025), (date(2022, 1, 1), 2021)],
)
def test_fiscal_year_of(end: date, year: int) -> None:
    assert fiscal_year_of(end) == year


class TestComputeRatio:
    def test_the_six_ratios(self) -> None:
        assert set(RATIOS) == {
            "net_margin",
            "operating_margin",
            "gross_margin",
            "revenue_growth",
            "current_ratio",
            "liabilities_to_assets",
        }

    def test_net_margin_for_a_year(self, facts: MemoryFacts) -> None:
        result = compute_ratio(facts, WORKIVA, "net_margin", 2024)
        assert result["value"] == round(-55042000 / 738680000, 4)
        assert result["numerator"]["value"] == -55042000
        assert result["denominator"]["value"] == 738680000
        assert result["accessions"] == ["0001445305-26-000016", "0001445305-26-000016"]

    def test_the_latest_year_is_the_default(self, facts: MemoryFacts) -> None:
        result = compute_ratio(facts, WORKIVA, "net_margin")
        assert result["fiscal_year"] == 2025
        assert result["value"] == round(-26169000 / 884568000, 4)

    def test_revenue_growth_uses_the_prior_year(self, facts: MemoryFacts) -> None:
        result = compute_ratio(facts, WORKIVA, "revenue_growth", 2025)
        assert result["value"] == round(884568000 / 738680000 - 1, 4)
        assert result["denominator"]["fiscal_year"] == 2024

    def test_a_missing_concept_is_named(self, facts: MemoryFacts) -> None:
        result = compute_ratio(facts, WORKIVA, "gross_margin", 2024)
        assert result["error"] == "missing_concept"
        assert result["missing"] == "gross_profit"

    def test_an_unknown_ratio_lists_the_known_ones(self, facts: MemoryFacts) -> None:
        result = compute_ratio(facts, WORKIVA, "price_to_earnings")
        assert result["error"] == "unknown_ratio"
        assert "net_margin" in result["detail"]

    def test_a_20f_filer_has_nothing_to_compute(self, facts: MemoryFacts) -> None:
        assert compute_ratio(facts, MONDAY, "net_margin")["error"] == "missing_concept"


def frames(respond_status: int = 200) -> RecordingHandler:
    return RecordingHandler(
        lambda _request: httpx.Response(respond_status, json=FRAME if respond_status == 200 else {})
    )


class TestFrameValues:
    def test_a_company_is_ranked_among_the_filers(self) -> None:
        handler = frames()
        result = frame_values(sec_client(handler, FakeClock()), AIRBNB, "net_income", 2024)
        assert str(handler.requests[0].url).endswith(
            "/frames/us-gaap/NetIncomeLoss/USD/CY2024.json"
        )
        assert result["frame"] == "CY2024"
        assert result["value"] == 2648349000
        assert result["rank"] == 7
        assert result["filer_count"] == 20
        assert result["median"] == -10523.0
        assert [entry["name"] for entry in result["largest"]] == [
            "TheRealReal, Inc.",
            "Alphabet Inc.",
            "HighPeak Energy, Inc.",
            "Apple Inc.",
            "BERKSHIRE HATHAWAY INC",
        ]
        assert "calendar 2024" in result["admits"]

    def test_an_off_cycle_year_is_in_the_frame_of_its_end(self) -> None:
        result = frame_values(sec_client(frames(), FakeClock()), GITLAB, "net_income", 2024)
        assert result["period_end"] == "2025-01-31"

    def test_an_instant_concept_uses_the_year_end_frame(self) -> None:
        handler = frames()
        frame_values(sec_client(handler, FakeClock()), AIRBNB, "total_assets", 2024)
        assert str(handler.requests[0].url).endswith("/Assets/USD/CY2024Q4I.json")

    def test_a_company_outside_the_frame_has_no_rank(self) -> None:
        result = frame_values(sec_client(frames(), FakeClock()), 42, "net_income", 2024)
        assert result["rank"] is None
        assert result["filer_count"] == 20

    def test_a_missing_frame_is_an_error_dict(self) -> None:
        result = frame_values(sec_client(frames(404), FakeClock()), AIRBNB, "net_income", 2024)
        assert result["error"] == "no_frame"

    def test_bad_arguments_are_error_dicts(self) -> None:
        client = sec_client(frames(), FakeClock())
        assert frame_values(client, AIRBNB, "net income", 2024)["error"] == "invalid_concept"
        assert frame_values(client, AIRBNB, "net_income", 1900)["error"] == "invalid_year"

    def test_an_unreachable_sec_raises(self) -> None:
        with sec_question_scope(cap=4, fault="sec_unreachable"), pytest.raises(SecUnavailable):
            frame_values(sec_client(frames(), FakeClock()), AIRBNB, "net_income", 2024)


class TestBoundTools:
    def test_the_tools_carry_their_names_docs_and_arguments(self, facts: MemoryFacts) -> None:
        context = ToolContext(facts=facts, sec=sec_client(frames(), FakeClock()), cik=WORKIVA)
        tools = bound_tools(context, ToolResultCollector())
        by_name = {t.__name__: t for t in [*tools.analyst, *tools.ranking]}
        assert [t.__name__ for t in tools.analyst] == ["query_facts", "compute_ratio"]
        assert [t.__name__ for t in tools.ranking] == ["frame_values"]
        assert "total_liabilities" in (by_name["query_facts"].__doc__ or "")
        assert list(inspect.signature(by_name["query_facts"]).parameters) == [
            "concept",
            "fiscal_year_from",
            "fiscal_year_to",
        ]

    def test_a_tool_runs_against_the_request_company_and_records(self, facts: MemoryFacts) -> None:
        context = ToolContext(facts=facts, sec=sec_client(frames(), FakeClock()), cik=WORKIVA)
        collector = ToolResultCollector()
        query = bound_tools(context, collector).analyst[0]
        result = query("net_income", 2019, 2019)
        assert result["rows"][0]["value"] == -47479000
        assert collector.results == [result]

    def test_a_failed_tool_is_named_and_raises(self) -> None:
        context = ToolContext(
            facts=MemoryFacts.of(), sec=sec_client(frames(), FakeClock()), cik=AIRBNB
        )
        collector = ToolResultCollector()
        frame = bound_tools(context, collector).ranking[0]
        with sec_question_scope(cap=4, fault="sec_unreachable"), pytest.raises(SecUnavailable):
            frame("net_income", 2024)
        assert collector.failed_tools == {"frame_values"}


def test_the_answer_accepts_only_ratios_compute_ratio_knows() -> None:
    assert set(get_args(RatioName.__value__)) == set(RATIOS)
    with pytest.raises(ValidationError):
        RatioUsed(name="net_income_rank", value=0.03, fiscal_year=2025, accessions=[])
