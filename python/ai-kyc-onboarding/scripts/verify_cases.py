"""Check each harness case's trace, logs and metrics in the collector's debug output.

Run by scripts/verify-scout.sh, and exits 1 when any check fails.
"""

import json
import re
import sys
from collections import Counter
from collections.abc import Callable, Collection, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, NamedTuple

from scripts.collector_debug import Attributes, LogRecord, Span, Telemetry, parse


RUN_WORKFLOW = "RunWorkflow:KycOnboardingWorkflow"
START_WORKFLOW = "StartWorkflow:KycOnboardingWorkflow"
CREATE_CASE = "POST /cases"
EXTRACTION_REQUEST = "RunActivity:agent__kyc-extraction__model_request"
ASSESSMENT_REQUEST = "RunActivity:agent__kyc-assessment__model_request"
TOOL_CALL = "RunActivity:agent__kyc-assessment__toolset__<agent>__call_tool"
EXTRACTION_AGENT = "invoke_agent kyc-extraction"
ASSESSMENT_AGENT = "invoke_agent kyc-assessment"
SCREEN_SANCTIONS = "execute_tool screen_sanctions"
DOCUMENT_RECEIVED = "kyc.document_received"
REVIEW_RECEIVED = "kyc.review_received"
AWAIT_DOCUMENTS = "kyc.await_documents"
ASSESS = "kyc.assess"
AWAIT_REVIEW = "kyc.await_review"
SIGNAL_HANDLER = "HandleSignal:submit_document"
UPDATE_HANDLER = "HandleUpdate:submit_review"
ERROR_STATUS = "Error"
WORKER_SERVICE = "ai-kyc-onboarding-worker"
SCOUT_EXPORTER = "otlp_http/b14"

ATTEMPT = "base14.temporal.activity.attempt"
ACTIVITY_ID = "temporalActivityID"
WORKFLOW_ID = "temporalWorkflowID"
OUTCOME = "base14.kyc.outcome"
ESCALATION_REASON = "base14.kyc.escalation_reason"
CASE_ID = "base14.kyc.case_id"
ACCOUNT_TYPE = "base14.kyc.account_type"
ASSESSMENT_DECISION = "base14.kyc.assessment_decision"
RISK_LEVEL = "base14.kyc.risk_level"
DOCUMENTS_TO_RESEND = "base14.kyc.documents_to_resend"
MISSING_DOCUMENTS = "base14.kyc.missing_documents"
SANCTIONS_RESULT = "base14.kyc.sanctions.result"
PROMPT_VERSION = "base14.prompt.version"
CONVERSATION_ID = "gen_ai.conversation.id"
PROVIDER_NAME = "gen_ai.provider.name"
ERROR_TYPE = "error.type"
GENAI_SPAN_PREFIXES = ("invoke_agent ", "chat ", "execute_tool ")
LOCAL_PROVIDER = "ollama"

SANCTIONS_DOWN_FAILED_ATTEMPTS = 3
MODEL_UNAVAILABLE_FAILED_ATTEMPTS = 2


@dataclass(frozen=True)
class LogLine:
    severity: str
    body: str
    span_name: str
    attributes: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class Expectation:
    """`documents` applies only when the harness result lacks `documents_sent`."""

    documents: int
    assessments: int
    reviewed: bool = False
    decided: bool = True
    calls_tools: bool = True
    lines: tuple[LogLine, ...] = ()


ESCALATED_FOR_RISK = (
    LogLine("WARN", "sanctions near match", TOOL_CALL),
    LogLine("WARN", "case escalated for review", ASSESS, ((ESCALATION_REASON, "risk"),)),
)

EXPECTATIONS: dict[str, Expectation] = {
    "auto_approved": Expectation(documents=2, assessments=1),
    "approved_after_resubmission": Expectation(documents=3, assessments=2),
    "approved_by_reviewer": Expectation(
        documents=2, assessments=1, reviewed=True, lines=ESCALATED_FOR_RISK
    ),
    "rejected_by_reviewer": Expectation(
        documents=2, assessments=1, reviewed=True, lines=ESCALATED_FOR_RISK
    ),
    "rejected_automatically": Expectation(documents=4, assessments=3),
    "expired": Expectation(
        documents=0,
        assessments=0,
        decided=False,
        calls_tools=False,
        lines=(LogLine("WARN", "document deadline passed", AWAIT_DOCUMENTS),),
    ),
    "worker_crash": Expectation(documents=3, assessments=1),
    "model_unavailable": Expectation(
        documents=2,
        assessments=1,
        lines=(LogLine("ERROR", "injected model_unavailable fault", EXTRACTION_REQUEST),),
    ),
    "sanctions_down": Expectation(
        documents=2,
        assessments=1,
        lines=(LogLine("ERROR", "injected sanctions_down fault", TOOL_CALL),),
    ),
    "tight_budget": Expectation(
        documents=2,
        assessments=1,
        reviewed=True,
        decided=False,
        calls_tools=False,
        lines=(
            LogLine("ERROR", "agent run failed", ASSESS),
            LogLine("WARN", "case escalated for review", ASSESS, ((ESCALATION_REASON, "budget"),)),
        ),
    ),
    "bad_output": Expectation(
        documents=2,
        assessments=1,
        lines=(LogLine("ERROR", "injected bad_output fault", EXTRACTION_REQUEST),),
    ),
}

ALL_SCENARIOS = tuple(EXPECTATIONS)


class RequiredDataPoint(NamedTuple):
    """A metric data point the run must hold, and the scenarios that produce it."""

    metric: str
    key: str
    value: str
    scenarios: tuple[str, ...]


APPROVED = (
    "auto_approved",
    "approved_after_resubmission",
    "approved_by_reviewer",
    "worker_crash",
    "model_unavailable",
    "sanctions_down",
    "tight_budget",
    "bad_output",
)
REJECTED = ("rejected_by_reviewer", "rejected_automatically")
ESCALATED_FOR_RISK_SCENARIOS = ("approved_by_reviewer", "rejected_by_reviewer")
SCREENED_CLEAR = (
    "auto_approved",
    "approved_after_resubmission",
    "worker_crash",
    "model_unavailable",
    "sanctions_down",
    "bad_output",
)

RESUBMISSION_SCENARIOS = ("approved_after_resubmission", "rejected_automatically")
DEADLINE_SCENARIOS = ("expired",)
SANCTIONS_RESULTS: dict[str, str] = {
    **dict.fromkeys(SCREENED_CLEAR, "clear"),
    **dict.fromkeys(ESCALATED_FOR_RISK_SCENARIOS, "near_match"),
}

REQUIRED_DATA_POINTS: tuple[RequiredDataPoint, ...] = (
    RequiredDataPoint("base14.kyc.cases", OUTCOME, "approved", APPROVED),
    RequiredDataPoint("base14.kyc.cases", OUTCOME, "rejected", REJECTED),
    RequiredDataPoint("base14.kyc.cases", OUTCOME, "expired", ("expired",)),
    RequiredDataPoint("base14.kyc.cases", ESCALATION_REASON, "risk", ESCALATED_FOR_RISK_SCENARIOS),
    RequiredDataPoint("base14.kyc.cases", ESCALATION_REASON, "budget", ("tight_budget",)),
    RequiredDataPoint("base14.kyc.case.duration", OUTCOME, "approved", APPROVED),
    RequiredDataPoint("base14.kyc.case.duration", OUTCOME, "expired", ("expired",)),
    RequiredDataPoint(
        "base14.kyc.resubmissions",
        "base14.kyc.document_type",
        "proof_of_address",
        ("approved_after_resubmission",),
    ),
    RequiredDataPoint(
        "base14.kyc.resubmissions", "base14.kyc.document_type", "id", ("rejected_automatically",)
    ),
    RequiredDataPoint(
        "base14.kyc.review.wait",
        "base14.kyc.review_decision",
        "approve",
        ("approved_by_reviewer", "tight_budget"),
    ),
    RequiredDataPoint(
        "base14.kyc.review.wait",
        "base14.kyc.review_decision",
        "reject",
        ("rejected_by_reviewer",),
    ),
    RequiredDataPoint(
        "base14.kyc.sanctions.checks", "base14.kyc.sanctions.result", "clear", SCREENED_CLEAR
    ),
    RequiredDataPoint(
        "base14.kyc.sanctions.checks",
        "base14.kyc.sanctions.result",
        "near_match",
        ESCALATED_FOR_RISK_SCENARIOS,
    ),
    RequiredDataPoint(
        "base14.kyc.sanctions.checks", "base14.kyc.sanctions.result", "error", ("sanctions_down",)
    ),
)


@dataclass
class Report:
    passed: int = 0
    failed: int = 0
    lines: list[str] = field(default_factory=list)

    def check(self, label: str, ok: bool, detail: str = "") -> bool:
        if ok:
            self.passed += 1
            self.lines.append(f"  PASS {label}")
        else:
            self.failed += 1
            self.lines.append(f"  FAIL {label}" + (f" ({detail})" if detail else ""))
        return ok

    def section(self, title: str) -> None:
        self.lines.append("")
        self.lines.append(f"=== {title} ===")


class CaseTrace:
    """The spans and log lines of one case's trace, found from its RunWorkflow span."""

    def __init__(self, telemetry: Telemetry, case_id: str, trace_id: str) -> None:
        self.case_id = case_id
        self.trace_id = trace_id
        self.spans = [span for span in telemetry.spans if span.trace_id == trace_id]
        self.logs = [log for log in telemetry.logs if log.trace_id == trace_id]
        self.by_id = {span.span_id: span for span in self.spans}

    def named(self, name: str) -> list[Span]:
        return [span for span in self.spans if span.name == name]

    def starting(self, prefix: str | tuple[str, ...]) -> list[Span]:
        return [span for span in self.spans if span.name.startswith(prefix)]

    def children(self, parent: Span, prefix: str) -> list[Span]:
        return [
            span
            for span in self.spans
            if span.parent_id == parent.span_id and span.name.startswith(prefix)
        ]

    def lines(self, body: str, severity: str) -> list[LogRecord]:
        return [log for log in self.logs if log.body.startswith(body) and log.severity == severity]

    def span_of(self, log: LogRecord) -> Span | None:
        return self.by_id.get(log.span_id)


def case_trace_ids(telemetry: Telemetry, case_id: str) -> list[str]:
    return sorted(
        {
            span.trace_id
            for span in telemetry.spans
            if span.name == RUN_WORKFLOW and span.attributes.get(WORKFLOW_ID) == case_id
        }
    )


def check_case(report: Report, telemetry: Telemetry, scenario: dict[str, Any]) -> str | None:
    name, case_id = scenario["scenario"], scenario["case_id"]
    trace_ids = case_trace_ids(telemetry, case_id)
    report.section(f"{name} case={case_id} trace={','.join(trace_ids) or 'none'}")
    if not report.check("one trace for the case", len(trace_ids) == 1, f"found {len(trace_ids)}"):
        return None
    trace = CaseTrace(telemetry, case_id, trace_ids[0])
    expectation = EXPECTATIONS[name]
    all_spans = {span.span_id: span for span in telemetry.spans}

    _check_trace_shape(report, trace)
    _check_span_names(report, trace, expectation)
    _check_wait_spans(report, trace, expectation)
    _check_arrival_links(
        report,
        trace,
        all_spans,
        DOCUMENT_RECEIVED,
        SIGNAL_HANDLER,
        int(scenario.get("documents_sent", expectation.documents)),
    )
    _check_arrival_links(
        report, trace, all_spans, REVIEW_RECEIVED, UPDATE_HANDLER, 1 if expectation.reviewed else 0
    )
    _check_case_lines(report, trace, expectation, scenario.get("outcome"))
    check_span_attributes(report, trace, name)
    FAILURE_CHECKS.get(name, _no_failure_checks)(report, trace, scenario)
    return trace.trace_id


def _check_trace_shape(report: Report, trace: CaseTrace) -> None:
    run_workflow = trace.named(RUN_WORKFLOW)
    report.check("one RunWorkflow span", len(run_workflow) == 1, f"found {len(run_workflow)}")
    roots = [span for span in trace.named(CREATE_CASE) if not span.parent_id]
    starts = [
        span
        for span in trace.named(START_WORKFLOW)
        if any(span.parent_id == root.span_id for root in roots)
    ]
    report.check(
        "trace rooted at POST /cases > StartWorkflow > RunWorkflow",
        bool(starts) and any(run.parent_id == starts[0].span_id for run in run_workflow),
    )
    duplicates = [
        span_id for span_id, count in Counter(s.span_id for s in trace.spans).items() if count > 1
    ]
    report.check("no duplicated span", not duplicates, f"duplicated {duplicates}")


def _check_span_names(report: Report, trace: CaseTrace, expectation: Expectation) -> None:
    expected = [CREATE_CASE, START_WORKFLOW, RUN_WORKFLOW, AWAIT_DOCUMENTS]
    if expectation.documents:
        expected.append(DOCUMENT_RECEIVED)
    if expectation.assessments:
        expected += [
            ASSESS,
            EXTRACTION_AGENT,
            ASSESSMENT_AGENT,
            "chat ",
            "StartActivity:agent__kyc-extraction__model_request",
            EXTRACTION_REQUEST,
            "StartActivity:agent__kyc-assessment__model_request",
            ASSESSMENT_REQUEST,
        ]
    if expectation.calls_tools:
        expected += [SCREEN_SANCTIONS, TOOL_CALL]
    if expectation.reviewed:
        expected += [AWAIT_REVIEW, REVIEW_RECEIVED]
    missing = [name for name in expected if not trace.starting(name)]
    report.check(f"expected span names ({len(expected)})", not missing, f"missing {missing}")


def _check_wait_spans(report: Report, trace: CaseTrace, expectation: Expectation) -> None:
    run_workflow = next(iter(trace.named(RUN_WORKFLOW)), None)
    expected = {
        AWAIT_DOCUMENTS: max(expectation.assessments, 1),
        ASSESS: expectation.assessments,
        AWAIT_REVIEW: 1 if expectation.reviewed else 0,
    }
    found = {name: len(trace.named(name)) for name in expected}
    report.check(
        "wait spans " + ", ".join(f"{name}={count}" for name, count in expected.items()),
        found == expected,
        f"found {found}",
    )
    stray = [
        span.name
        for name in expected
        for span in trace.named(name)
        if run_workflow is None or span.parent_id != run_workflow.span_id
    ]
    report.check("wait spans are children of RunWorkflow", not stray, f"not under it: {stray}")


def _check_arrival_links(
    report: Report,
    trace: CaseTrace,
    all_spans: dict[str, Span],
    arrival: str,
    handler: str,
    expected: int,
) -> None:
    arrivals = trace.named(arrival)
    if expected == 0:
        report.check(f"no {arrival} spans", not arrivals, f"found {len(arrivals)}")
        return
    report.check(
        f"{arrival} spans = {expected}", len(arrivals) == expected, f"found {len(arrivals)}"
    )
    unresolved = []
    for span in arrivals:
        linked = [all_spans.get(link.span_id) for link in span.links]
        resolved = [
            target
            for target in linked
            if target is not None
            and target.name == handler
            and target.trace_id != trace.trace_id
            and target.attributes.get(WORKFLOW_ID) == trace.case_id
        ]
        if len(span.links) != 1 or len(resolved) != 1:
            unresolved.append(span.span_id)
    report.check(
        f"each {arrival} links to its {handler} span in the request's trace",
        not unresolved,
        f"unresolved on {unresolved}",
    )


def _check_case_lines(
    report: Report, trace: CaseTrace, expectation: Expectation, outcome: str | None
) -> None:
    _check_line_on(report, trace, LogLine("INFO", "case created", CREATE_CASE))
    _check_line_on(
        report, trace, LogLine("INFO", "case closed", RUN_WORKFLOW, ((OUTCOME, str(outcome)),))
    )
    if expectation.documents:
        _check_line_on(report, trace, LogLine("INFO", "documents complete", AWAIT_DOCUMENTS))
    if expectation.decided:
        _check_line_on(report, trace, LogLine("INFO", "assessment decided", ASSESS))
    for line in expectation.lines:
        _check_line_on(report, trace, line)
    off_span = [
        f"{log.severity} {log.body!r}"
        for log in trace.logs
        if log.severity in ("WARN", "ERROR") and trace.span_of(log) is None
    ]
    report.check(
        "every WARN and ERROR line sits on a span of the case trace",
        not off_span,
        f"off span: {off_span}",
    )


def _check_line_on(report: Report, trace: CaseTrace, line: LogLine) -> None:
    records = trace.lines(line.body, line.severity)
    misplaced = [
        log
        for log in records
        if (span := trace.span_of(log)) is None or span.name != line.span_name
    ]
    wrong_attributes = [
        log
        for log in records
        if any(str(log.attributes.get(key)) != value for key, value in line.attributes)
    ]
    label = f"{line.severity} {line.body!r} on {line.span_name}"
    if line.attributes:
        label += " with " + ", ".join(f"{key}={value}" for key, value in line.attributes)
    report.check(
        label,
        bool(records) and not misplaced and not wrong_attributes,
        f"{len(records)} lines, {len(misplaced)} on another span, {len(wrong_attributes)} with other attributes",
    )


def check_span_attributes(report: Report, trace: CaseTrace, scenario: str) -> None:
    """The business and GenAI attributes each scenario puts on its spans."""
    expectation = EXPECTATIONS[scenario]
    roots = [span for span in trace.named(CREATE_CASE) if not span.parent_id]
    report.check(
        f"{CREATE_CASE} carries {CASE_ID} and {ACCOUNT_TYPE}",
        bool(roots)
        and all(
            r.attributes.get(CASE_ID) == trace.case_id and r.attributes.get(ACCOUNT_TYPE)
            for r in roots
        ),
        f"found {[(r.attributes.get(CASE_ID), r.attributes.get(ACCOUNT_TYPE)) for r in roots]}",
    )
    if expectation.assessments:
        _check_genai_attributes(report, trace)
    if expectation.decided:
        undecided = [
            s.span_id for s in trace.named(ASSESS) if not s.attributes.get(ASSESSMENT_DECISION)
        ]
        report.check(
            f"every {ASSESS} carries {ASSESSMENT_DECISION}",
            not undecided,
            f"missing on {undecided}",
        )
    if scenario in ESCALATED_FOR_RISK_SCENARIOS:
        _check_decision_attributes(
            report,
            trace,
            "escalate",
            lambda a: bool(a.get(RISK_LEVEL)) and a.get(ESCALATION_REASON) == "risk",
            f"{RISK_LEVEL} and {ESCALATION_REASON}=risk",
        )
    if scenario in RESUBMISSION_SCENARIOS:
        _check_decision_attributes(
            report,
            trace,
            "request_resubmission",
            lambda a: bool(a.get(DOCUMENTS_TO_RESEND)),
            DOCUMENTS_TO_RESEND,
        )
    if scenario in DEADLINE_SCENARIOS:
        waits = trace.named(AWAIT_DOCUMENTS)
        report.check(
            f"{AWAIT_DOCUMENTS} carries {MISSING_DOCUMENTS} once the deadline passes",
            bool(waits) and all(w.attributes.get(MISSING_DOCUMENTS) for w in waits),
        )
    if expectation.calls_tools:
        _check_sanctions_attributes(report, trace, SANCTIONS_RESULTS.get(scenario))


def _check_genai_attributes(report: Report, trace: CaseTrace) -> None:
    genai = trace.starting(GENAI_SPAN_PREFIXES)
    other_conversation = sorted(
        {s.name for s in genai if s.attributes.get(CONVERSATION_ID) != trace.case_id}
    )
    report.check(
        f"every GenAI span ({len(genai)}) carries {CONVERSATION_ID}=<case id>",
        bool(genai) and not other_conversation,
        f"not on {other_conversation}",
    )
    chats = trace.starting("chat ")
    providers = sorted({str(s.attributes.get(PROVIDER_NAME)) for s in chats})
    report.check(
        f"every chat span names {PROVIDER_NAME}={LOCAL_PROVIDER}",
        providers == [LOCAL_PROVIDER],
        f"found {providers}",
    )
    runs = trace.starting("invoke_agent ")
    unversioned = [s.name for s in runs if not s.attributes.get(PROMPT_VERSION)]
    report.check(
        f"every invoke_agent span carries {PROMPT_VERSION}",
        bool(runs) and not unversioned,
        f"missing on {unversioned}",
    )


def _check_decision_attributes(
    report: Report,
    trace: CaseTrace,
    decision: str,
    carries: Callable[[Attributes], bool],
    label: str,
) -> None:
    decided = [s for s in trace.named(ASSESS) if s.attributes.get(ASSESSMENT_DECISION) == decision]
    report.check(
        f"{ASSESS} deciding {decision} carries {label}",
        bool(decided) and all(carries(s.attributes) for s in decided),
        f"{len(decided)} {decision} spans",
    )


def _check_sanctions_attributes(report: Report, trace: CaseTrace, on_success: str | None) -> None:
    """Failed attempts carry `error`. A successful one carries `on_success` when the scenario
    fixes the screening result, and any result otherwise."""
    attempts = [
        attempt
        for tool in trace.named(SCREEN_SANCTIONS)
        for start in trace.children(tool, "StartActivity:")
        for attempt in trace.children(start, TOOL_CALL)
    ]
    found = [(a.status, a.attributes.get(SANCTIONS_RESULT)) for a in attempts]
    wrong = [
        (status, result)
        for status, result in found
        if result is None
        or (status == ERROR_STATUS and result != "error")
        or (status != ERROR_STATUS and on_success is not None and result != on_success)
    ]
    report.check(
        f"every screen_sanctions attempt carries {SANCTIONS_RESULT}"
        + (f", {on_success} on success" if on_success else ""),
        bool(attempts) and not wrong,
        f"{len(attempts)} attempts, wrong {wrong}",
    )


def _no_failure_checks(report: Report, trace: CaseTrace, scenario: dict[str, Any]) -> None:
    return None


def _failed_attempts_with_a_line_each(
    report: Report, trace: CaseTrace, activity: str, fault_line: str, failures_per_call: int
) -> None:
    attempts = trace.named(activity)
    by_parent: dict[str, list[Span]] = {}
    for span in attempts:
        by_parent.setdefault(span.parent_id, []).append(span)
    retried = [
        spans for spans in by_parent.values() if any(s.status == ERROR_STATUS for s in spans)
    ]
    shapes = [
        sorted((int(s.attributes.get(ATTEMPT, 0)), s.status == ERROR_STATUS) for s in spans)
        for spans in retried
    ]
    expected_shape = [(n, True) for n in range(1, failures_per_call + 1)] + [
        (failures_per_call + 1, False)
    ]
    report.check(
        f"{activity}: attempts 1-{failures_per_call} with error status, then attempt "
        f"{failures_per_call + 1} succeeds",
        bool(shapes) and all(shape == expected_shape for shape in shapes),
        f"found {shapes}",
    )
    failed = {s.span_id for spans in retried for s in spans if s.status == ERROR_STATUS}
    lines = trace.lines(fault_line, "ERROR")
    on_failed = Counter(log.span_id for log in lines if log.span_id in failed)
    report.check(
        f"one ERROR {fault_line!r} line on each failed attempt span ({len(failed)})",
        bool(failed) and len(lines) == len(failed) and set(on_failed) == failed,
        f"{len(lines)} lines on {len(on_failed)} of {len(failed)} failed spans",
    )


def _model_unavailable(report: Report, trace: CaseTrace, scenario: dict[str, Any]) -> None:
    _failed_attempts_with_a_line_each(
        report,
        trace,
        EXTRACTION_REQUEST,
        "injected model_unavailable fault",
        MODEL_UNAVAILABLE_FAILED_ATTEMPTS,
    )


def _sanctions_down(report: Report, trace: CaseTrace, scenario: dict[str, Any]) -> None:
    screenings = len(trace.named(SCREEN_SANCTIONS))
    failed = [s for s in trace.named(TOOL_CALL) if s.status == ERROR_STATUS]
    report.check(
        f"three failed screen_sanctions attempts per screening ({screenings})",
        screenings > 0 and len(failed) == SANCTIONS_DOWN_FAILED_ATTEMPTS * screenings,
        f"{len(failed)} failed attempts",
    )
    _failed_attempts_with_a_line_each(
        report, trace, TOOL_CALL, "injected sanctions_down fault", SANCTIONS_DOWN_FAILED_ATTEMPTS
    )


def _tight_budget(report: Report, trace: CaseTrace, scenario: dict[str, Any]) -> None:
    agents = trace.named(ASSESSMENT_AGENT)
    report.check(
        f"{ASSESSMENT_AGENT} has error status from the usage limit",
        len(agents) == 1 and agents[0].status == ERROR_STATUS,
        f"statuses {[a.status for a in agents]}",
    )
    report.check(
        f"{ASSESSMENT_AGENT} carries {ERROR_TYPE}",
        len(agents) == 1 and "UsageLimitExceeded" in str(agents[0].attributes.get(ERROR_TYPE)),
        f"found {[a.attributes.get(ERROR_TYPE) for a in agents]}",
    )
    assess = trace.named(ASSESS)
    report.check(
        f"{ASSESS} carries {ESCALATION_REASON}=budget",
        len(assess) == 1 and assess[0].attributes.get(ESCALATION_REASON) == "budget",
    )


def _bad_output(report: Report, trace: CaseTrace, scenario: dict[str, Any]) -> None:
    runs = trace.named(EXTRACTION_AGENT)
    chats = [chat for run in runs for chat in trace.children(run, "chat ")]
    report.check(
        f"one extra extraction chat span for the output retry ({len(runs)} runs)",
        len(chats) == len(runs) + 1,
        f"{len(chats)} chat spans",
    )


def _worker_crash(report: Report, trace: CaseTrace, scenario: dict[str, Any]) -> None:
    span_workers = {
        s.resource.instance for s in trace.spans if s.resource.service == WORKER_SERVICE
    }
    report.check(
        "spans from both worker processes in the one trace",
        len(span_workers) == 2,
        f"{len(span_workers)} worker instances",
    )
    log_workers = {
        log.resource.instance for log in trace.logs if log.resource.service == WORKER_SERVICE
    }
    report.check(
        "log lines from both worker processes in the one trace",
        len(log_workers) == 2,
        f"{len(log_workers)} worker instances",
    )
    crashed = scenario.get("crashed_activity") or {}
    activity_id, attempt = str(crashed.get("activity_id")), int(crashed.get("attempt") or 0)
    reruns = [
        s for s in trace.starting("RunActivity:") if s.attributes.get(ACTIVITY_ID) == activity_id
    ]
    report.check(
        f"killed activity {activity_id} shows only its rerun, attempt {attempt + 1}",
        bool(crashed)
        and [int(s.attributes.get(ATTEMPT, 0)) for s in reruns] == [attempt + 1]
        and reruns[0].status != ERROR_STATUS,
        f"attempts {[s.attributes.get(ATTEMPT) for s in reruns]}",
    )


FAILURE_CHECKS = {
    "model_unavailable": _model_unavailable,
    "sanctions_down": _sanctions_down,
    "tight_budget": _tight_budget,
    "bad_output": _bad_output,
    "worker_crash": _worker_crash,
}


def check_metrics(
    report: Report, telemetry: Telemetry, scenarios: Collection[str] | None = None
) -> None:
    """Checks the required data points, limited to `scenarios` when given."""
    report.section("Application metrics")
    for point in REQUIRED_DATA_POINTS:
        label = f"{point.metric} {{{point.key}={point.value}}}"
        if scenarios is not None and not set(point.scenarios) & set(scenarios):
            report.lines.append(f"  SKIP {label} (no scenario in this run produces it)")
            continue
        points = [
            p
            for p in telemetry.data_points
            if p.metric == point.metric and str(p.attributes.get(point.key)) == point.value
        ]
        report.check(label, bool(points), "no data points")


_SELF_METRIC = re.compile(
    r"^otelcol_exporter_(sent|send_failed)_(\w+?)(?:_total)?\{([^}]*)\}\s+(\S+)$"
)


def exporter_counts(prometheus_text: str) -> dict[tuple[str, str], float]:
    counts: dict[tuple[str, str], float] = {}
    for line in prometheus_text.splitlines():
        match = _SELF_METRIC.match(line)
        if match and f'exporter="{SCOUT_EXPORTER}"' in match.group(3):
            outcome, signal, _, value = match.groups()
            counts[outcome, signal] = counts.get((outcome, signal), 0) + float(value)
    return counts


def check_exporter(
    report: Report, telemetry: Telemetry, prometheus_text: str, prometheus_text_at_start: str | None
) -> None:
    """Send counts are the growth since test-api.sh recorded the cumulative counters."""
    report.section(f"Scout exporter ({SCOUT_EXPORTER})")
    if not prometheus_text:
        report.lines.append("  SKIP no collector self-metrics given, send counts not checked")
    elif prometheus_text_at_start is None:
        report.check(
            "the harness recorded the exporter counters at the start of the run",
            False,
            "missing from the run file",
        )
    else:
        counts = exporter_counts(prometheus_text)
        at_start = exporter_counts(prometheus_text_at_start)
        for signal in ("spans", "log_records", "metric_points"):
            sent, failed = (
                counts.get((outcome, signal), 0) - at_start.get((outcome, signal), 0)
                for outcome in ("sent", "send_failed")
            )
            report.check(f"sent {signal} during the run: {sent:.0f}", sent > 0, "nothing sent")
            report.check(f"failed {signal} during the run: {failed:.0f}", failed == 0)
    errors = [line for line in telemetry.collector_warnings if SCOUT_EXPORTER in line]
    report.check(
        "no exporter warnings or errors in the collector log", not errors, f"{len(errors)} lines"
    )


def check_run_complete(report: Report, run: dict[str, Any], *, allow_partial: bool) -> None:
    report.section("Harness run")
    ran = {scenario["scenario"] for scenario in run["scenarios"]}
    if not ran:
        report.check("the run recorded at least one scenario", False, "none recorded")
        return
    if allow_partial:
        report.lines.append(
            f"  SKIP partial run allowed, {len(ran)} of {len(ALL_SCENARIOS)} scenarios"
        )
        return
    missing = [name for name in ALL_SCENARIOS if name not in ran]
    report.check(
        f"the run holds all {len(ALL_SCENARIOS)} scenarios",
        not missing,
        f"missing: {', '.join(missing)}",
    )


def verify(
    run: dict[str, Any], telemetry: Telemetry, prometheus_text: str, *, allow_partial: bool = False
) -> Report:
    report = Report()
    check_run_complete(report, run, allow_partial=allow_partial)
    check_exporter(report, telemetry, prometheus_text, run.get("collector_self_metrics_at_start"))
    trace_ids: dict[str, str | None] = {}
    for scenario in run["scenarios"]:
        trace_ids[scenario["scenario"]] = check_case(report, telemetry, scenario)
    ran = {scenario["scenario"] for scenario in run["scenarios"]}
    check_metrics(report, telemetry, ran if allow_partial else None)
    report.section("Cases")
    for scenario in run["scenarios"]:
        report.lines.append(
            f"  {scenario['scenario']:<28} case={scenario['case_id']} "
            f"trace={trace_ids[scenario['scenario']]}"
        )
    return report


def _read_lines(path: Path) -> Iterator[str]:
    with path.open(encoding="utf-8", errors="replace") as handle:
        yield from handle


def main(argv: list[str]) -> int:
    allow_partial = "--allow-partial" in argv
    run_file, collector_log, collector_metrics = (
        Path(arg) for arg in argv if arg != "--allow-partial"
    )
    run = json.loads(run_file.read_text(encoding="utf-8"))
    report = verify(
        run,
        parse(_read_lines(collector_log)),
        collector_metrics.read_text(encoding="utf-8"),
        allow_partial=allow_partial,
    )
    print("\n".join(report.lines))
    print("")
    print(f"=== Summary: {report.passed} passed, {report.failed} failed ===")
    return 1 if report.failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
