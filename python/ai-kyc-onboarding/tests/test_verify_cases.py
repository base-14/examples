import json
from itertools import count
from pathlib import Path
from typing import Any

import pytest

from scripts.collector_debug import DataPoint, Link, LogRecord, Resource, Span, Telemetry
from scripts.verify_cases import (
    ALL_SCENARIOS,
    ASSESSMENT_DECISION,
    CONVERSATION_ID,
    DOCUMENTS_TO_RESEND,
    ERROR_TYPE,
    ESCALATION_REASON,
    MISSING_DOCUMENTS,
    OUTCOME,
    PROMPT_VERSION,
    PROVIDER_NAME,
    REQUIRED_DATA_POINTS,
    RISK_LEVEL,
    SANCTIONS_RESULT,
    CaseTrace,
    Report,
    _tight_budget,
    check_case,
    check_exporter,
    check_metrics,
    check_run_complete,
    check_span_attributes,
    exporter_counts,
    main,
)
from scripts.verify_cases import (
    CASE_ID as CASE_ID_ATTRIBUTE,
)


CASE_ID = "case-1"
TRACE_ID = "trace-case"
API = Resource({"service.name": "ai-kyc-onboarding-api", "service.instance.id": "api-1"})
WORKER = Resource({"service.name": "ai-kyc-onboarding-worker", "service.instance.id": "worker-1"})
RESTARTED_WORKER = Resource(
    {"service.name": "ai-kyc-onboarding-worker", "service.instance.id": "worker-2"}
)


CREATE_CASE_ATTRIBUTES = {CASE_ID_ATTRIBUTE: CASE_ID, "base14.kyc.account_type": "personal"}
RUN_ATTRIBUTES = {CONVERSATION_ID: CASE_ID, PROMPT_VERSION: "v1"}
CHAT_ATTRIBUTES = {CONVERSATION_ID: CASE_ID, PROVIDER_NAME: "ollama"}
TOOL_ATTRIBUTES = {CONVERSATION_ID: CASE_ID}


class CaseBuilder:
    """Builds the telemetry of one case the way the stack exports it."""

    def __init__(self) -> None:
        self.telemetry = Telemetry()
        self._ids = count(1)

    def span(
        self,
        name: str,
        parent: Span | None = None,
        *,
        resource: Resource = WORKER,
        status: str = "Unset",
        trace_id: str = TRACE_ID,
        **attributes: str | int,
    ) -> Span:
        span = Span(
            resource=resource,
            trace_id=trace_id,
            parent_id=parent.span_id if parent else "",
            span_id=f"s{next(self._ids)}",
            name=name,
            status=status,
            attributes=dict(attributes),
        )
        self.telemetry.spans.append(span)
        return span

    def log(
        self,
        severity: str,
        body: str,
        span: Span,
        *,
        resource: Resource = WORKER,
        **attributes: str,
    ) -> LogRecord:
        record = LogRecord(
            resource=resource,
            severity=severity,
            body=body,
            trace_id=span.trace_id,
            span_id=span.span_id,
            attributes=dict(attributes),
        )
        self.telemetry.logs.append(record)
        return record

    def arrival(self, name: str, parent: Span, handler: str) -> None:
        sender = self.span(handler, resource=WORKER, trace_id=f"trace-{name}-{next(self._ids)}")
        sender.attributes["temporalWorkflowID"] = CASE_ID
        arrival = self.span(name, parent)
        arrival.links.append(Link(trace_id=sender.trace_id, span_id=sender.span_id))

    def activity(
        self, chat: Span, activity_type: str, attempts: list[str], *, activity_id: str = "1"
    ) -> list[Span]:
        start = self.span(f"StartActivity:{activity_type}", chat)
        return [
            self.span(
                f"RunActivity:{activity_type}",
                start,
                status=status,
                temporalActivityID=activity_id,
                **{"base14.temporal.activity.attempt": attempt},
            )
            for attempt, status in enumerate(attempts, start=1)
        ]

    def approved_case(
        self,
        *,
        documents: int = 2,
        sanctions_attempts: list[str] | None = None,
        extraction_chats: tuple[int, ...] = (1, 1),
        worker_after_assessment: Resource = WORKER,
    ) -> dict[str, Any]:
        post = self.span("POST /cases", resource=API, **CREATE_CASE_ATTRIBUTES)
        start = self.span("StartWorkflow:KycOnboardingWorkflow", post, resource=API)
        run = self.span(
            "RunWorkflow:KycOnboardingWorkflow", start, resource=worker_after_assessment
        )
        run.attributes["temporalWorkflowID"] = CASE_ID
        self.log("INFO", "case created", post, resource=API)

        waiting = self.span("kyc.await_documents", run)
        for _ in range(documents):
            self.arrival("kyc.document_received", waiting, "HandleSignal:submit_document")
        self.log("INFO", "documents complete", waiting)

        assess = self.span("kyc.assess", run, **{ASSESSMENT_DECISION: "approve"})
        for chats in extraction_chats:
            extraction = self.span("invoke_agent kyc-extraction", assess, **RUN_ATTRIBUTES)
            for _ in range(chats):
                chat = self.span("chat gemma4:e2b", extraction, **CHAT_ATTRIBUTES)
                self.activity(chat, "agent__kyc-extraction__model_request", ["Unset"])
        assessment = self.span("invoke_agent kyc-assessment", assess, **RUN_ATTRIBUTES)
        chat = self.span(
            "chat qwen3.5:9B", assessment, resource=worker_after_assessment, **CHAT_ATTRIBUTES
        )
        self.activity(chat, "agent__kyc-assessment__model_request", ["Unset"])
        tool = self.span("execute_tool screen_sanctions", assessment, **TOOL_ATTRIBUTES)
        tool_attempts = self.activity(
            tool,
            "agent__kyc-assessment__toolset__<agent>__call_tool",
            sanctions_attempts or ["Unset"],
            activity_id="5",
        )
        for attempt in tool_attempts:
            attempt.attributes[SANCTIONS_RESULT] = "error" if attempt.status == "Error" else "clear"
            if attempt.status == "Error":
                self.log("ERROR", "injected sanctions_down fault", attempt)
        self.log("INFO", "assessment decided approve", assess, resource=worker_after_assessment)
        self.log(
            "INFO",
            "case closed",
            run,
            resource=worker_after_assessment,
            **{"base14.kyc.outcome": "approved"},
        )
        return {"scenario": "auto_approved", "case_id": CASE_ID, "outcome": "approved"}


def _failures(report: Report) -> list[str]:
    return [line for line in report.lines if line.startswith("  FAIL")]


def _run(builder: CaseBuilder, scenario: dict[str, Any]) -> Report:
    report = Report()
    check_case(report, builder.telemetry, scenario)
    return report


class TestSuccessCase:
    def test_a_complete_approved_case_passes_every_check(self) -> None:
        builder = CaseBuilder()
        scenario = builder.approved_case()

        report = _run(builder, scenario)

        assert _failures(report) == []
        assert report.passed > 10

    def test_a_case_split_across_two_traces_fails(self) -> None:
        builder = CaseBuilder()
        scenario = builder.approved_case()
        builder.span("RunWorkflow:KycOnboardingWorkflow", trace_id="other").attributes[
            "temporalWorkflowID"
        ] = CASE_ID

        report = _run(builder, scenario)

        assert _failures(report) == ["  FAIL one trace for the case (found 2)"]

    def test_a_missing_close_line_fails(self) -> None:
        builder = CaseBuilder()
        scenario = builder.approved_case()
        builder.telemetry.logs = [
            log for log in builder.telemetry.logs if log.body != "case closed"
        ]

        failures = _failures(_run(builder, scenario))

        assert len(failures) == 1
        assert "'case closed'" in failures[0]

    def test_an_arrival_link_that_resolves_nowhere_fails(self) -> None:
        builder = CaseBuilder()
        scenario = builder.approved_case()
        next(s for s in builder.telemetry.spans if s.name == "kyc.document_received").links[
            0
        ].span_id = "gone"

        failures = _failures(_run(builder, scenario))

        assert len(failures) == 1
        assert "links to its HandleSignal:submit_document" in failures[0]


class TestDocumentsSent:
    def test_counts_the_documents_the_harness_sent(self) -> None:
        builder = CaseBuilder()
        scenario = builder.approved_case(documents=3)
        scenario["documents_sent"] = 3

        assert _failures(_run(builder, scenario)) == []

    def test_fewer_arrival_spans_than_documents_sent_fails(self) -> None:
        builder = CaseBuilder()
        scenario = builder.approved_case(documents=2)
        scenario["documents_sent"] = 3

        assert _failures(_run(builder, scenario)) == [
            "  FAIL kyc.document_received spans = 3 (found 2)"
        ]


class TestSanctionsDown:
    def test_three_failed_attempts_with_an_error_line_each_pass(self) -> None:
        builder = CaseBuilder()
        scenario = builder.approved_case(sanctions_attempts=["Error", "Error", "Error", "Unset"])
        scenario["scenario"] = "sanctions_down"

        assert _failures(_run(builder, scenario)) == []

    def test_a_failed_attempt_without_its_error_line_fails(self) -> None:
        builder = CaseBuilder()
        scenario = builder.approved_case(sanctions_attempts=["Error", "Error", "Error", "Unset"])
        scenario["scenario"] = "sanctions_down"
        builder.telemetry.logs.remove(
            next(log for log in builder.telemetry.logs if log.severity == "ERROR")
        )

        failures = _failures(_run(builder, scenario))

        assert len(failures) == 1
        assert (
            "one ERROR 'injected sanctions_down fault' line on each failed attempt" in failures[0]
        )

    def test_a_retry_without_error_status_fails(self) -> None:
        builder = CaseBuilder()
        scenario = builder.approved_case(sanctions_attempts=["Error", "Error", "Unset", "Unset"])
        scenario["scenario"] = "sanctions_down"

        failures = _failures(_run(builder, scenario))

        assert any("three failed screen_sanctions attempts" in line for line in failures)


class TestBadOutput:
    def test_counts_one_extra_chat_under_the_extraction_agent(self) -> None:
        builder = CaseBuilder()
        scenario = builder.approved_case(extraction_chats=(2, 1))
        scenario["scenario"] = "bad_output"
        builder.log(
            "ERROR",
            "injected bad_output fault",
            next(
                s
                for s in builder.telemetry.spans
                if s.name.startswith("RunActivity:agent__kyc-extraction")
            ),
        )

        assert _failures(_run(builder, scenario)) == []

    def test_assessment_retries_do_not_count(self) -> None:
        builder = CaseBuilder()
        scenario = builder.approved_case(extraction_chats=(1, 1))
        scenario["scenario"] = "bad_output"
        assessment = next(
            s for s in builder.telemetry.spans if s.name == "invoke_agent kyc-assessment"
        )
        builder.span("chat qwen3.5:9B", assessment)

        failures = _failures(_run(builder, scenario))

        assert any("one extra extraction chat span" in line for line in failures)


class TestWorkerCrash:
    def _crash_case(self, restarted: Resource) -> tuple[CaseBuilder, dict[str, Any]]:
        builder = CaseBuilder()
        scenario = builder.approved_case(
            documents=3, extraction_chats=(1, 1, 1), worker_after_assessment=restarted
        )
        scenario["scenario"] = "worker_crash"
        rerun = next(
            s
            for s in builder.telemetry.spans
            if s.name == "RunActivity:agent__kyc-assessment__model_request"
        )
        rerun.resource = restarted
        rerun.attributes.update({"temporalActivityID": "4", "base14.temporal.activity.attempt": 2})
        scenario["crashed_activity"] = {"activity_id": "4", "attempt": 1}
        return builder, scenario

    def test_one_trace_with_both_workers_and_the_rerun_passes(self) -> None:
        builder, scenario = self._crash_case(RESTARTED_WORKER)

        assert _failures(_run(builder, scenario)) == []

    def test_a_trace_from_one_worker_fails_both_process_checks(self) -> None:
        builder, scenario = self._crash_case(WORKER)

        failures = _failures(_run(builder, scenario))

        assert len(failures) == 2
        assert all("both worker processes" in line for line in failures)


def _first(builder: CaseBuilder, prefix: str) -> Span:
    return next(s for s in builder.telemetry.spans if s.name.startswith(prefix))


def _attribute_failures(builder: CaseBuilder, scenario: str) -> list[str]:
    report = Report()
    check_span_attributes(report, CaseTrace(builder.telemetry, CASE_ID, TRACE_ID), scenario)
    return _failures(report)


class TestSpanAttributes:
    def test_the_approved_case_carries_every_attribute(self) -> None:
        builder = CaseBuilder()
        builder.approved_case()

        assert _attribute_failures(builder, "auto_approved") == []

    @pytest.mark.parametrize(
        ("span_prefix", "key", "failure"),
        [
            ("POST /cases", CASE_ID_ATTRIBUTE, "POST /cases carries base14.kyc.case_id"),
            ("chat ", CONVERSATION_ID, "every GenAI span"),
            ("execute_tool ", CONVERSATION_ID, "every GenAI span"),
            ("chat ", PROVIDER_NAME, "every chat span names gen_ai.provider.name=ollama"),
            ("invoke_agent ", PROMPT_VERSION, "every invoke_agent span carries"),
            ("kyc.assess", ASSESSMENT_DECISION, "every kyc.assess carries"),
            ("RunActivity:agent__kyc-assessment__toolset", SANCTIONS_RESULT, "screen_sanctions"),
        ],
    )
    def test_a_missing_attribute_fails(self, span_prefix: str, key: str, failure: str) -> None:
        builder = CaseBuilder()
        builder.approved_case()
        del _first(builder, span_prefix).attributes[key]

        failures = _attribute_failures(builder, "auto_approved")

        assert len(failures) == 1
        assert failure in failures[0]

    def test_a_hosted_provider_fails_the_local_provider_check(self) -> None:
        builder = CaseBuilder()
        builder.approved_case()
        _first(builder, "chat ").attributes[PROVIDER_NAME] = "openai"

        (failure,) = _attribute_failures(builder, "auto_approved")

        assert "found ['ollama', 'openai']" in failure

    def test_a_near_match_in_a_clear_scenario_fails(self) -> None:
        builder = CaseBuilder()
        builder.approved_case()
        _first(builder, "RunActivity:agent__kyc-assessment__toolset").attributes[
            SANCTIONS_RESULT
        ] = "near_match"

        (failure,) = _attribute_failures(builder, "auto_approved")

        assert "clear on success" in failure

    def test_a_failed_screening_attempt_must_carry_error(self) -> None:
        builder = CaseBuilder()
        builder.approved_case(sanctions_attempts=["Error", "Error", "Error", "Unset"])
        _first(builder, "RunActivity:agent__kyc-assessment__toolset").attributes[
            SANCTIONS_RESULT
        ] = "clear"

        (failure,) = _attribute_failures(builder, "sanctions_down")

        assert "wrong [('Error', 'clear')]" in failure

    def _escalated_case(self) -> CaseBuilder:
        builder = CaseBuilder()
        builder.approved_case()
        _first(builder, "kyc.assess").attributes.update(
            {ASSESSMENT_DECISION: "escalate", RISK_LEVEL: "medium", ESCALATION_REASON: "risk"}
        )
        _first(builder, "RunActivity:agent__kyc-assessment__toolset").attributes[
            SANCTIONS_RESULT
        ] = "near_match"
        return builder

    def test_an_escalation_for_risk_with_its_level_and_reason_passes(self) -> None:
        assert _attribute_failures(self._escalated_case(), "approved_by_reviewer") == []

    @pytest.mark.parametrize("key", [RISK_LEVEL, ESCALATION_REASON])
    def test_an_escalation_for_risk_without_its_level_or_reason_fails(self, key: str) -> None:
        builder = self._escalated_case()
        del _first(builder, "kyc.assess").attributes[key]

        (failure,) = _attribute_failures(builder, "rejected_by_reviewer")

        assert "kyc.assess deciding escalate carries base14.kyc.risk_level" in failure

    def _resubmission_case(self, documents_to_resend: str | None) -> CaseBuilder:
        builder = CaseBuilder()
        builder.approved_case()
        first_round = builder.span(
            "kyc.assess",
            _first(builder, "RunWorkflow:"),
            **{ASSESSMENT_DECISION: "request_resubmission"},
        )
        if documents_to_resend is not None:
            first_round.attributes[DOCUMENTS_TO_RESEND] = documents_to_resend
        return builder

    def test_a_resubmission_naming_its_documents_passes(self) -> None:
        builder = self._resubmission_case('["proof_of_address"]')

        assert _attribute_failures(builder, "approved_after_resubmission") == []

    def test_a_resubmission_without_its_documents_fails(self) -> None:
        builder = self._resubmission_case(None)

        (failure,) = _attribute_failures(builder, "approved_after_resubmission")

        assert "deciding request_resubmission carries base14.kyc.documents_to_resend" in failure

    def _expired_case(self, missing: str | None) -> CaseBuilder:
        builder = CaseBuilder()
        post = builder.span("POST /cases", resource=API, **CREATE_CASE_ATTRIBUTES)
        start = builder.span("StartWorkflow:KycOnboardingWorkflow", post, resource=API)
        run = builder.span("RunWorkflow:KycOnboardingWorkflow", start)
        waiting = builder.span("kyc.await_documents", run)
        if missing is not None:
            waiting.attributes[MISSING_DOCUMENTS] = missing
        return builder

    def test_an_expired_case_naming_its_missing_documents_passes(self) -> None:
        builder = self._expired_case('["id", "proof_of_address"]')

        assert _attribute_failures(builder, "expired") == []

    def test_an_expired_case_without_its_missing_documents_fails(self) -> None:
        (failure,) = _attribute_failures(self._expired_case(None), "expired")

        assert "kyc.await_documents carries base14.kyc.missing_documents" in failure


class TestTightBudget:
    def _budget_case(self, error_type: str | None) -> tuple[CaseBuilder, dict[str, Any]]:
        builder = CaseBuilder()
        scenario = builder.approved_case()
        run = _first(builder, "invoke_agent kyc-assessment")
        run.status = "Error"
        if error_type is not None:
            run.attributes[ERROR_TYPE] = error_type
        _first(builder, "kyc.assess").attributes[ESCALATION_REASON] = "budget"
        return builder, scenario

    def test_the_failed_run_typed_as_a_usage_limit_passes(self) -> None:
        builder, scenario = self._budget_case("pydantic_ai.exceptions.UsageLimitExceeded")
        report = Report()

        _tight_budget(report, CaseTrace(builder.telemetry, CASE_ID, TRACE_ID), scenario)

        assert _failures(report) == []

    def test_the_failed_run_without_error_type_fails(self) -> None:
        builder, scenario = self._budget_case(None)
        report = Report()

        _tight_budget(report, CaseTrace(builder.telemetry, CASE_ID, TRACE_ID), scenario)

        assert _failures(report) == [
            "  FAIL invoke_agent kyc-assessment carries error.type (found [None])"
        ]


class TestMetrics:
    def test_every_required_data_point_present_passes(self) -> None:
        telemetry = Telemetry(
            data_points=[
                DataPoint(point.metric, {point.key: point.value}) for point in REQUIRED_DATA_POINTS
            ]
        )
        report = Report()

        check_metrics(report, telemetry)

        assert report.failed == 0

    def test_a_missing_sanctions_error_point_fails(self) -> None:
        telemetry = Telemetry(
            data_points=[
                DataPoint(point.metric, {point.key: point.value})
                for point in REQUIRED_DATA_POINTS
                if point.value != "error"
            ]
        )
        report = Report()

        check_metrics(report, telemetry)

        assert _failures(report) == [
            "  FAIL base14.kyc.sanctions.checks {base14.kyc.sanctions.result=error} (no data points)"
        ]

    def test_every_required_data_point_names_a_scenario_that_produces_it(self) -> None:
        for point in REQUIRED_DATA_POINTS:
            assert point.scenarios
            assert set(point.scenarios) <= set(ALL_SCENARIOS)

    def test_a_partial_run_checks_only_what_its_scenarios_produce(self) -> None:
        telemetry = Telemetry(
            data_points=[
                DataPoint("base14.kyc.cases", {OUTCOME: "approved"}),
                DataPoint("base14.kyc.case.duration", {OUTCOME: "approved"}),
            ]
        )
        report = Report()

        check_metrics(report, telemetry, scenarios={"worker_crash"})

        assert _failures(report) == [
            "  FAIL base14.kyc.sanctions.checks {base14.kyc.sanctions.result=clear} (no data points)"
        ]
        assert (
            "  SKIP base14.kyc.cases {base14.kyc.outcome=expired} (no scenario in this run produces it)"
            in report.lines
        )
        assert report.passed == 2

    def test_a_partial_run_still_fails_a_point_its_scenarios_produce(self) -> None:
        report = Report()

        check_metrics(report, Telemetry(), scenarios={"expired"})

        assert _failures(report) == [
            "  FAIL base14.kyc.cases {base14.kyc.outcome=expired} (no data points)",
            "  FAIL base14.kyc.case.duration {base14.kyc.outcome=expired} (no data points)",
        ]

    def test_main_limits_metric_checks_only_with_allow_partial(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        run_file = tmp_path / "last-run.json"
        run_file.write_text(json.dumps(_run_file(("expired",))))
        empty = tmp_path / "empty"
        empty.write_text("")
        args = [str(run_file), str(empty), str(empty)]

        main(args)
        strict = capsys.readouterr().out
        main(["--allow-partial", *args])
        allowed = capsys.readouterr().out

        risk = "base14.kyc.cases {base14.kyc.escalation_reason=risk}"
        assert f"FAIL {risk} (no data points)" in strict
        assert f"SKIP {risk} (no scenario in this run produces it)" in allowed


SELF_METRICS = """\
otelcol_exporter_sent_spans{exporter="debug"} 900
otelcol_exporter_sent_spans{exporter="otlp_http/b14",server_address="x",url_path="/a"} 500
otelcol_exporter_sent_log_records_total{exporter="otlp_http/b14",server_address="x"} 40
otelcol_exporter_sent_metric_points{exporter="otlp_http/b14"} 3000
otelcol_exporter_send_failed_spans{exporter="otlp_http/b14"} 2
"""

SELF_METRICS_AT_START = """\
otelcol_exporter_sent_spans{exporter="otlp_http/b14",server_address="x",url_path="/a"} 100
otelcol_exporter_sent_metric_points{exporter="otlp_http/b14"} 1000
"""


class TestExporter:
    def test_sums_the_scout_exporter_counts_only(self) -> None:
        assert exporter_counts(SELF_METRICS) == {
            ("sent", "spans"): 500,
            ("sent", "log_records"): 40,
            ("sent", "metric_points"): 3000,
            ("send_failed", "spans"): 2,
        }

    def test_failed_sends_and_exporter_warnings_fail(self) -> None:
        telemetry = Telemetry(
            collector_warnings=[
                '2026-09-24T13:00:00Z\twarn\tExporting failed\t{"otelcol.component.id": "otlp_http/b14"}'
            ]
        )
        report = Report()

        check_exporter(report, telemetry, SELF_METRICS, SELF_METRICS_AT_START)

        assert _failures(report) == [
            "  FAIL failed spans during the run: 2",
            "  FAIL no exporter warnings or errors in the collector log (1 lines)",
        ]

    def test_counts_only_what_the_run_itself_sent(self) -> None:
        report = Report()

        check_exporter(report, Telemetry(), SELF_METRICS, SELF_METRICS_AT_START)

        assert "  PASS sent spans during the run: 400" in report.lines
        assert "  PASS sent log_records during the run: 40" in report.lines

    def test_nothing_sent_during_the_run_fails_despite_earlier_sends(self) -> None:
        report = Report()

        check_exporter(report, Telemetry(), SELF_METRICS_AT_START, SELF_METRICS_AT_START)

        assert "  FAIL sent spans during the run: 0 (nothing sent)" in _failures(report)

    def test_failures_from_before_the_run_do_not_count(self) -> None:
        report = Report()

        check_exporter(report, Telemetry(), SELF_METRICS, SELF_METRICS)

        assert "  PASS failed spans during the run: 0" in report.lines

    def test_a_run_without_counters_from_its_start_fails(self) -> None:
        report = Report()

        check_exporter(report, Telemetry(), SELF_METRICS, None)

        assert _failures(report) == [
            "  FAIL the harness recorded the exporter counters at the start of the run "
            "(missing from the run file)"
        ]


def _run_file(scenarios: tuple[str, ...]) -> dict[str, Any]:
    return {"scenarios": [{"scenario": name, "case_id": name} for name in scenarios]}


class TestRunComplete:
    def test_a_run_of_all_eleven_scenarios_passes(self) -> None:
        report = Report()

        check_run_complete(report, _run_file(ALL_SCENARIOS), allow_partial=False)

        assert len(ALL_SCENARIOS) == 11
        assert _failures(report) == []

    def test_a_partial_run_fails(self) -> None:
        report = Report()

        check_run_complete(report, _run_file(("auto_approved", "bad_output")), allow_partial=False)

        (failure,) = _failures(report)
        assert failure.startswith("  FAIL the run holds all 11 scenarios (missing: ")
        assert "expired" in failure

    def test_a_partial_run_passes_when_allowed(self) -> None:
        report = Report()

        check_run_complete(report, _run_file(("auto_approved",)), allow_partial=True)

        assert _failures(report) == []
        assert "  SKIP partial run allowed, 1 of 11 scenarios" in report.lines

    @pytest.mark.parametrize("allow_partial", [False, True])
    def test_a_run_with_no_scenarios_fails(self, allow_partial: bool) -> None:
        report = Report()

        check_run_complete(report, _run_file(()), allow_partial=allow_partial)

        assert _failures(report) == [
            "  FAIL the run recorded at least one scenario (none recorded)"
        ]

    def test_main_reads_the_allow_partial_flag(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        run_file = tmp_path / "last-run.json"
        run_file.write_text(json.dumps(_run_file(("expired",))))
        empty = tmp_path / "empty"
        empty.write_text("")
        args = [str(run_file), str(empty), str(empty)]

        main(args)
        strict = capsys.readouterr().out
        main(["--allow-partial", *args])
        allowed = capsys.readouterr().out

        assert "FAIL the run holds all 11 scenarios" in strict
        assert "SKIP partial run allowed, 1 of 11 scenarios" in allowed
        assert "FAIL the run holds all 11 scenarios" not in allowed
