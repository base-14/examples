import logging
from typing import Any

import pytest
from fastapi.testclient import TestClient
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode

from filing_analyst.agents import RANKING_UNAVAILABLE
from filing_analyst.telemetry import QuestionIdFilter, instrument_fastapi_app, question_logging
from tests.api_support import KALTURA, Rig, Scripts
from tests.metric_capture import captured_metrics, total
from tests.scripted_model import Call, Say, tool_results
from tests.span_capture import captured_spans, named
from tests.test_agents import ANSWER, LOOKUP


EMPTY_ANSWER = Call(
    "FilingAnswer",
    {
        "answer": "The filings do not report headcount by region.",
        "figures": [],
        "ratios": [],
        "caveats": ["Searched the annual 10-K facts for headcount."],
    },
)
RANK = Call("rank_among_filers", {"input": "Rank Workiva Inc. on net_income for 2024."})
FRAME_CALL = Call("frame_values", {"concept": "net_income", "year": 2024})
SERVER_SPAN = "POST /questions"
QUESTIONS = "base14.filing.questions"
OUTCOME = "base14.filing.outcome"


@pytest.fixture(autouse=True)
def user_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SEC_USER_AGENT", "Example Co ops@example.com")


@pytest.fixture
def spans() -> InMemorySpanExporter:
    return captured_spans()


@pytest.fixture
def meters() -> InMemoryMetricReader:
    return captured_metrics()


def ask(rig: Rig, **body: Any) -> Any:
    app = rig.app()
    instrument_fastapi_app(app)
    with TestClient(app) as client:
        return client.post("/questions", json={"ticker": "WK", "question": "Net income?", **body})


def server_span(spans: InMemorySpanExporter) -> ReadableSpan:
    (span,) = [s for s in spans.get_finished_spans() if s.name == SERVER_SPAN]
    return span


def attributes(span: ReadableSpan) -> dict[str, Any]:
    return dict(span.attributes or {})


class TestAnswered:
    def test_a_grounded_answer_is_served(
        self, spans: InMemorySpanExporter, meters: InMemoryMetricReader
    ) -> None:
        before = total(meters, QUESTIONS, **{OUTCOME: "answered"})
        response = ask(Rig(Scripts([LOOKUP, ANSWER])))
        assert response.status_code == 200
        body = response.json()
        assert body["outcome"] == "answered"
        assert body["figures"][0]["accession"] == "0001445305-22-000041"
        assert body["question_id"].startswith("q-")
        assert body["facts_source"] == "stored"
        assert body["sec_calls"] == 0
        assert body["rankings"] == []
        server = attributes(server_span(spans))
        assert server[OUTCOME] == "answered"
        assert server["base14.filing.question_id"] == body["question_id"]
        assert server["base14.filing.ticker"] == "WK"
        assert server["base14.filing.sec_calls"] == 0
        (verify,) = named(spans.get_finished_spans(), "filing.verify_answer")
        assert attributes(verify)["base14.filing.figure_count"] == 1
        assert attributes(verify)["base14.filing.citations_verified"] == 1
        assert total(meters, QUESTIONS, **{OUTCOME: "answered"}) == before + 1
        assert total(meters, "base14.filing.question.duration", **{OUTCOME: "answered"}) >= 1

    def test_an_answer_with_no_figures_is_not_available(self, spans: InMemorySpanExporter) -> None:
        response = ask(Rig(Scripts([EMPTY_ANSWER])), ticker="MNDY", question="Headcount?")
        assert response.status_code == 200
        assert response.json()["outcome"] == "not_available"
        assert attributes(server_span(spans))[OUTCOME] == "not_available"

    def test_sql_text_in_the_question_is_passed_through_as_text(
        self, spans: InMemorySpanExporter
    ) -> None:
        question = "Net income?'; DROP TABLE facts; --"
        scripts = Scripts([LOOKUP, ANSWER])
        response = ask(Rig(scripts), question=question)
        assert response.status_code == 200
        first_prompt = scripts.analyst.seen[0][0]["content"][0]["text"]
        assert question in first_prompt

    def test_the_first_question_on_a_cached_company_loads_it_without_the_sec(
        self, spans: InMemorySpanExporter, meters: InMemoryMetricReader
    ) -> None:
        rig = Rig(Scripts([EMPTY_ANSWER]))
        before = total(meters, "base14.filing.facts.loaded")
        ask(rig, ticker="MNDY", question="Headcount?")
        assert rig.store.loads[0][1] == "cache"
        assert rig.sec.requests == []
        assert total(meters, "base14.filing.facts.loaded") > before


class TestSec:
    def test_a_company_outside_the_cache_is_fetched_from_the_sec(
        self, spans: InMemorySpanExporter, meters: InMemoryMetricReader
    ) -> None:
        rig = Rig(Scripts([EMPTY_ANSWER]))
        before = total(
            meters,
            "base14.filing.sec.requests",
            **{"base14.sec.endpoint": "companyfacts", "http.response.status_code": 200},
        )
        response = ask(rig, ticker="KLTR")
        assert response.status_code == 200
        assert rig.store.loads == [(KALTURA, "sec")]
        assert response.json()["facts_source"] == "sec"
        assert response.json()["sec_calls"] == 1
        assert attributes(server_span(spans))["base14.filing.sec_calls"] == 1
        after = total(
            meters,
            "base14.filing.sec.requests",
            **{"base14.sec.endpoint": "companyfacts", "http.response.status_code": 200},
        )
        assert after == before + 1

    def test_sec_down_retries_then_answers(self, spans: InMemorySpanExporter) -> None:
        rig = Rig(Scripts([EMPTY_ANSWER]))
        response = ask(rig, ticker="KLTR", fault="sec_down")
        assert response.status_code == 200
        assert len(rig.sec.requests) == 1
        client_spans = [
            s for s in spans.get_finished_spans() if "base14.sec.endpoint" in attributes(s)
        ]
        assert [attributes(s)["base14.sec.attempt"] for s in client_spans] == [1, 2, 3]
        assert [s.status.status_code for s in client_spans] == [
            StatusCode.ERROR,
            StatusCode.ERROR,
            StatusCode.UNSET,
        ]
        server = server_span(spans)
        assert all(s.parent and s.parent.span_id == server.context.span_id for s in client_spans)

    def test_sec_blocked_is_502_then_503_inside_the_back_off(
        self, spans: InMemorySpanExporter, caplog: pytest.LogCaptureFixture
    ) -> None:
        rig = Rig(Scripts([EMPTY_ANSWER]))
        app = rig.app()
        with TestClient(app) as client:
            blocked = client.post(
                "/questions",
                json={"ticker": "KLTR", "question": "Revenue?", "fault": "sec_blocked"},
            )
            inside = client.post("/questions", json={"ticker": "AMPL", "question": "Revenue?"})
        assert blocked.status_code == 502
        assert blocked.json()["reason"] == "sec_unavailable"
        assert blocked.json()["outcome"] == "error"
        assert inside.status_code == 503
        assert inside.json()["reason"] == "sec_backoff"
        assert "SEC back-off in force" in caplog.text
        assert rig.sec.requests == []
        assert rig.scripts.analyst.seen == []

    def test_sec_unreachable_in_the_ranking_leaves_the_analyst_running(
        self, spans: InMemorySpanExporter, meters: InMemoryMetricReader
    ) -> None:
        before = total(meters, "base14.filing.rankings", **{OUTCOME: "not_available"})
        scripts = Scripts([RANK, EMPTY_ANSWER], [FRAME_CALL, Say("The frame is unavailable.")])
        response = ask(Rig(scripts), fault="sec_unreachable")
        assert response.status_code == 200
        assert response.json()["outcome"] == "not_available"
        assert RANKING_UNAVAILABLE in response.json()["caveats"]
        (frame_tool,) = named(spans.get_finished_spans(), "execute_tool frame_values")
        assert frame_tool.status.status_code == StatusCode.ERROR
        after = total(meters, "base14.filing.rankings", **{OUTCOME: "not_available"})
        assert after == before + 1

    def test_a_failed_frames_fetch_reaches_the_analyst_as_unavailable(self) -> None:
        scripts = Scripts([RANK, EMPTY_ANSWER], [FRAME_CALL, Say("Workiva ranked 3 of 20 filers.")])
        ask(Rig(scripts), fault="sec_unreachable")
        (rank_result,) = tool_results(scripts.analyst)
        assert rank_result["content"] == [{"text": RANKING_UNAVAILABLE}]

    def test_a_ranking_reply_reaches_the_analyst_with_the_frame_facts(self) -> None:
        scripts = Scripts([RANK, EMPTY_ANSWER], [FRAME_CALL, Say("Workiva ranked 3 of 20 filers.")])
        response = ask(Rig(scripts), ticker="ABNB")
        (ranking,) = response.json()["rankings"]
        (rank_result,) = tool_results(scripts.analyst)
        texts = [block["text"] for block in rank_result["content"]]
        assert "ranked 3 of 20" in texts[0]
        assert texts[-1] == (
            f"Frame CY2024, which admits every fiscal year ending in calendar 2024: rank "
            f"{ranking['rank']} of 20 filers, value {ranking['value']}, "
            f"accession {ranking['accession']}."
        )


class TestRefused:
    def test_an_unknown_ticker_is_404_before_any_model_call(
        self, spans: InMemorySpanExporter, meters: InMemoryMetricReader
    ) -> None:
        rig = Rig(Scripts([LOOKUP, ANSWER]))
        before = total(meters, QUESTIONS, **{OUTCOME: "rejected"})
        response = ask(rig, ticker="NOPE")
        assert response.status_code == 404
        assert response.json()["reason"] == "unknown_ticker"
        assert rig.scripts.analyst.seen == []
        assert not named(spans.get_finished_spans(), "invoke_agent analyst")
        assert attributes(server_span(spans))[OUTCOME] == "rejected"
        assert total(meters, QUESTIONS, **{OUTCOME: "rejected"}) == before + 1

    def test_an_over_long_question_is_422(self, spans: InMemorySpanExporter) -> None:
        response = ask(Rig(), question="x" * 501)
        assert response.status_code == 422
        assert response.json()["reason"] == "question_too_long"

    def test_a_malformed_body_is_422(self, spans: InMemorySpanExporter) -> None:
        app = Rig().app()
        with TestClient(app) as client:
            response = client.post("/questions", json={"ticker": "WK"})
        assert response.status_code == 422

    def test_faults_and_overrides_are_refused_when_disabled(
        self, spans: InMemorySpanExporter
    ) -> None:
        for override in ({"fault": "slow_model"}, {"call_budget": 3}, {"timeout_seconds": 1}):
            response = ask(Rig(faults_enabled=False), **override)
            assert response.status_code == 422
            assert response.json()["reason"] == "faults_disabled"

    def test_an_unknown_fault_is_422(self, spans: InMemorySpanExporter) -> None:
        response = ask(Rig(), fault="meteor_strike")
        assert response.status_code == 422
        assert response.json()["reason"] == "unknown_fault"


class TestModelFailures:
    @pytest.mark.parametrize(
        ("changes", "status", "outcome", "reason"),
        [
            ({"fault": "model_unavailable"}, 502, "error", "model_unavailable"),
            ({"fault": "bad_output"}, 502, "error", "bad_output"),
            ({"fault": "ungrounded_answer"}, 502, "ungrounded", "ungrounded"),
            ({"fault": "tight_budget"}, 504, "budget", "budget"),
            ({"fault": "slow_model", "timeout_seconds": 0.2}, 504, "timeout", "timeout"),
        ],
    )
    def test_each_failure_maps_to_its_status_and_outcome(
        self,
        spans: InMemorySpanExporter,
        meters: InMemoryMetricReader,
        changes: dict[str, Any],
        status: int,
        outcome: str,
        reason: str,
    ) -> None:
        before = total(meters, QUESTIONS, **{OUTCOME: outcome})
        response = ask(Rig(Scripts([LOOKUP, ANSWER, ANSWER, ANSWER])), **changes)
        assert response.status_code == status
        assert response.json()["outcome"] == outcome
        assert response.json()["reason"] == reason
        assert attributes(server_span(spans))[OUTCOME] == outcome
        assert total(meters, QUESTIONS, **{OUTCOME: outcome}) == before + 1

    def test_an_ungrounded_answer_is_recorded_on_the_verify_span(
        self, spans: InMemorySpanExporter
    ) -> None:
        ask(Rig(Scripts([LOOKUP, ANSWER])), fault="ungrounded_answer")
        (verify,) = named(spans.get_finished_spans(), "filing.verify_answer")
        assert attributes(verify)["base14.filing.rejection_reason"] == "accession_not_in_run"


class TestUnexpectedFailures:
    def test_a_store_failure_is_a_500_with_an_outcome(
        self, spans: InMemorySpanExporter, meters: InMemoryMetricReader
    ) -> None:
        rig = Rig(Scripts([LOOKUP, ANSWER]))

        def unreachable(_ticker: str) -> None:
            raise OSError("connection refused")

        rig.store.resolve_ticker = unreachable  # type: ignore[method-assign]
        before = total(meters, QUESTIONS, **{OUTCOME: "error"})
        response = ask(rig)
        assert response.status_code == 500
        assert response.json()["reason"] == "internal"
        assert attributes(server_span(spans))[OUTCOME] == "error"
        assert total(meters, QUESTIONS, **{OUTCOME: "error"}) == before + 1


class TestFacts:
    def test_stored_facts_are_served_for_a_concept(self) -> None:
        with TestClient(Rig().app()) as client:
            response = client.get("/companies/wk/facts", params={"concept": "net_income"})
        assert response.status_code == 200
        body = response.json()
        assert body["cik"] == 1445305
        assert body["rows"]

    @pytest.mark.parametrize(
        ("ticker", "concept", "status", "reason"),
        [
            ("NOPE", "net_income", 404, "unknown_ticker"),
            ("MNDY", "net_income", 404, "not_loaded"),
            ("WK", "net income; DROP TABLE facts", 422, "invalid_concept"),
        ],
    )
    def test_refusals(self, ticker: str, concept: str, status: int, reason: str) -> None:
        with TestClient(Rig().app()) as client:
            response = client.get(f"/companies/{ticker}/facts", params={"concept": concept})
        assert response.status_code == status
        assert response.json()["reason"] == reason


def test_log_records_carry_the_question_id() -> None:
    record = logging.LogRecord("filing_analyst", logging.INFO, __file__, 1, "x", None, None)
    with question_logging("q-abc"):
        exported = QuestionIdFilter().filter(record)
    assert isinstance(exported, logging.LogRecord)
    assert getattr(exported, "base14.filing.question_id") == "q-abc"
    outside = logging.LogRecord("filing_analyst", logging.INFO, __file__, 1, "x", None, None)
    exported = QuestionIdFilter().filter(outside)
    assert isinstance(exported, logging.LogRecord)
    assert not hasattr(exported, "base14.filing.question_id")


def test_a_ranking_is_reported_with_its_placement(spans: InMemorySpanExporter) -> None:
    scripts = Scripts([RANK, EMPTY_ANSWER], [FRAME_CALL, Say("Ranked.")])
    response = ask(Rig(scripts), ticker="ABNB")
    assert response.status_code == 200
    body = response.json()
    assert body["outcome"] == "answered"
    (ranking,) = body["rankings"]
    assert ranking["frame"] == "CY2024"
    assert ranking["filer_count"] == 20
    assert set(ranking) == {"concept", "frame", "rank", "filer_count", "value", "accession"}
    assert RANKING_UNAVAILABLE not in body["caveats"]
    assert (
        "The ranking is among every filer in frame CY2024, which admits every fiscal year "
        "ending in calendar 2024, not among industry peers."
    ) in body["caveats"]
