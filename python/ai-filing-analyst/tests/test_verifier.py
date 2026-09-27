import json
from typing import Any
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError
from strands.hooks import AfterToolCallEvent

from filing_analyst.answer import Figure, FilingAnswer, RatioUsed
from filing_analyst.verifier import ToolResultCollector, verify_answer


REVENUE_2024 = {
    "concept": "RevenueFromContractWithCustomerExcludingAssessedTax",
    "value": 738680000,
    "unit": "USD",
    "period_start": "2024-01-01",
    "period_end": "2024-12-31",
    "fiscal_year": 2024,
    "form": "10-K",
    "accession": "0001445305-26-000016",
    "filed": "2026-02-20",
}
NET_INCOME_2024 = {**REVENUE_2024, "concept": "NetIncomeLoss", "value": -55042000}
QUERY_RESULT = {"concept": "revenue", "rows": [REVENUE_2024], "total_rows": 1}
RATIO_RESULT = {
    "ratio": "net_margin",
    "fiscal_year": 2024,
    "value": -0.0745,
    "numerator": NET_INCOME_2024,
    "denominator": REVENUE_2024,
    "accessions": ["0001445305-26-000016", "0001445305-26-000016"],
}
FRAME_RESULT = {
    "concept": "NetIncomeLoss",
    "frame": "CY2024",
    "admits": "every fiscal year ending in calendar 2024",
    "filer_count": 6060,
    "median": -11150.5,
    "largest": [{"name": "Alphabet Inc.", "value": 100118000000}],
    "value": -55042000,
    "rank": 5310,
    "period_end": "2024-12-31",
    "accession": "0001445305-26-000030",
}


def revenue_figure(**changes: Any) -> Figure:
    fields: dict[str, Any] = {
        "concept": "revenue",
        "value": 738680000,
        "unit": "USD",
        "fiscal_year": 2024,
        "form": "10-K",
        "accession": "0001445305-26-000016",
    }
    return Figure(**{**fields, **changes})


def answer(text: str, *figures: Figure, ratios: list[RatioUsed] | None = None) -> FilingAnswer:
    return FilingAnswer(answer=text, figures=list(figures), ratios=ratios or [], caveats=[])


class TestVerifier:
    def test_a_clean_answer_passes(self) -> None:
        verdict = verify_answer(
            answer("Workiva reported revenue of $738,680,000 in fiscal 2024.", revenue_figure()),
            [QUERY_RESULT],
        )
        assert verdict.passed
        assert verdict.reason is None
        assert (verdict.figure_count, verdict.citations_verified) == (1, 1)

    def test_a_figure_no_tool_returned_is_rejected(self) -> None:
        verdict = verify_answer(
            answer("Revenue was $800,000,000.", revenue_figure(value=800000000)), [QUERY_RESULT]
        )
        assert not verdict.passed
        assert verdict.reason == "figure_not_returned"

    def test_a_figure_labelled_with_another_fiscal_year_is_rejected(self) -> None:
        verdict = verify_answer(
            answer(
                "Workiva reported revenue of $738,680,000 in fiscal 2025.",
                revenue_figure(fiscal_year=2025),
            ),
            [QUERY_RESULT],
        )
        assert not verdict.passed
        assert verdict.reason == "figure_not_returned"

    def test_a_ratio_citing_no_accession_is_rejected(self) -> None:
        ratio = RatioUsed(name="net_margin", fiscal_year=2024, value=-0.0745, accessions=[])
        verdict = verify_answer(answer("Net margin was -7.45%.", ratios=[ratio]), [RATIO_RESULT])
        assert not verdict.passed
        assert verdict.reason == "ratio_not_computed"

    def test_an_accession_number_not_in_the_run_is_rejected(self) -> None:
        verdict = verify_answer(
            answer("Revenue was $738,680,000.", revenue_figure(accession="0009999999-26-000001")),
            [QUERY_RESULT],
        )
        assert not verdict.passed
        assert verdict.reason == "accession_not_in_run"

    def test_a_number_in_the_text_missing_from_the_figures_is_rejected(self) -> None:
        verdict = verify_answer(
            answer("Revenue was $738,680,000, up 21% on the year.", revenue_figure()),
            [QUERY_RESULT],
        )
        assert not verdict.passed
        assert verdict.reason == "number_not_in_figures"

    @pytest.mark.parametrize(
        "text",
        [
            "Workiva reported revenue of $738.7 million in fiscal 2024.",
            "Workiva reported revenue of $738.68 million in fiscal 2024.",
            "Workiva reported revenue of $0.74 billion in fiscal 2024.",
            "Workiva reported revenue of $739M in fiscal 2024.",
        ],
    )
    def test_a_rounded_figure_in_the_text_passes(self, text: str) -> None:
        assert verify_answer(answer(text, revenue_figure()), [QUERY_RESULT]).passed

    def test_a_rounding_off_by_more_than_the_last_digit_is_rejected(self) -> None:
        verdict = verify_answer(
            answer("Workiva reported revenue of $738.9 million.", revenue_figure()),
            [QUERY_RESULT],
        )
        assert verdict.reason == "number_not_in_figures"

    def test_a_ratio_as_a_percentage_and_a_loss_without_its_sign_pass(self) -> None:
        net_income = revenue_figure(concept="net_income", value=-55042000)
        ratio = RatioUsed(
            name="net_margin",
            value=-0.0745,
            fiscal_year=2024,
            accessions=["0001445305-26-000016", "0001445305-26-000016"],
        )
        text = (
            "On December 31, 2024 Workiva's net loss of $55.0 million on revenue of "
            "$738.7 million gave a net margin of -7.45%, or about 7.5% negative."
        )
        verdict = verify_answer(
            answer(text, net_income, revenue_figure(), ratios=[ratio]), [RATIO_RESULT]
        )
        assert verdict.passed, verdict.reason

    def test_a_ratio_no_tool_computed_is_rejected(self) -> None:
        ratio = RatioUsed(
            name="net_margin",
            value=-0.08,
            fiscal_year=2024,
            accessions=["0001445305-26-000016"],
        )
        verdict = verify_answer(answer("Net margin was -8%.", ratios=[ratio]), [RATIO_RESULT])
        assert verdict.reason == "ratio_not_computed"

    def test_numbers_from_a_ranking_pass(self) -> None:
        figure = revenue_figure(
            concept="net_income", value=-55042000, accession="0001445305-26-000030"
        )
        text = (
            "Workiva ranked 5310 of 6060 filers in frame CY2024, with a net loss of "
            "$55.04 million against a median of -$11,150.5 and a largest filer at $100.1 billion."
        )
        assert verify_answer(answer(text, figure), [FRAME_RESULT]).passed

    def test_a_not_available_answer_with_no_numbers_passes(self) -> None:
        verdict = verify_answer(
            answer("The filings hold no headcount by region for Workiva."), [QUERY_RESULT]
        )
        assert verdict.passed
        assert verdict.figure_count == 0


def test_an_accession_number_must_have_the_sec_shape() -> None:
    with pytest.raises(ValidationError):
        revenue_figure(accession="0001445305-26")


def _event(name: str, result: dict[str, Any]) -> AfterToolCallEvent:
    return AfterToolCallEvent(
        agent=MagicMock(),
        selected_tool=None,
        tool_use={"toolUseId": "t-1", "name": name, "input": {}},
        invocation_state={},
        result=result,  # type: ignore[arg-type]
    )


class TestCollector:
    def test_json_tool_results_are_collected(self) -> None:
        collector = ToolResultCollector()
        collector.collect(
            _event(
                "query_facts",
                {
                    "toolUseId": "t-1",
                    "status": "success",
                    "content": [{"text": json.dumps(QUERY_RESULT)}],
                },
            )
        )
        assert collector.results == [QUERY_RESULT]

    def test_errors_text_and_the_answer_tool_are_skipped(self) -> None:
        collector = ToolResultCollector()
        collector.collect(
            _event(
                "query_facts", {"toolUseId": "t", "status": "error", "content": [{"text": "boom"}]}
            )
        )
        collector.collect(
            _event(
                "rank_among_filers",
                {
                    "toolUseId": "t",
                    "status": "success",
                    "content": [{"text": "Workiva ranks low."}],
                },
            )
        )
        collector.collect(
            _event(
                "FilingAnswer", {"toolUseId": "t", "status": "success", "content": [{"text": "{}"}]}
            )
        )
        assert collector.results == []
