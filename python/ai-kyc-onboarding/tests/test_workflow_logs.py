"""Case log lines from the workflow and its activities, read from an in-memory log exporter."""

import pytest
from opentelemetry.sdk._logs import ReadableLogRecord
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.trace import StatusCode

from kyc_onboarding.agents import StaticFaultRegistry
from kyc_onboarding.attributes import (
    ACTIVITY_ATTEMPT_ATTRIBUTE,
    ASSESSMENT_DECISION_ATTRIBUTE,
    CASE_ID_ATTRIBUTE,
    ESCALATION_REASON_ATTRIBUTE,
    OUTCOME_ATTRIBUTE,
)
from kyc_onboarding.models import CaseFault, CaseOutcome, CaseStatus, EscalationReason
from kyc_onboarding.worker import create_worker
from tests._telemetry_support import (
    captured_logs,
    captured_spans,
    log_attribute,
    log_body,
    named,
    only,
    span_id,
    trace_id,
)
from tests._workflow_support import (
    ScriptedAssessment,
    ScriptedExtraction,
    build_test_agents,
    case_input,
    required_documents,
    send_documents,
    start_case,
    time_skipping_env,
    wait_for_status,
)


TASK_QUEUE = "kyc-logs-test"
RUN_WORKFLOW = "RunWorkflow:KycOnboardingWorkflow"
FAILED_TOOL_ACTIVITY = "RunActivity:agent__kyc-assessment__toolset__<agent>__call_tool"
FAILED_MODEL_ACTIVITY = "RunActivity:agent__kyc-extraction__model_request"

pytestmark = pytest.mark.usefixtures("sanctions_clear")


async def _run_case(
    case_id: str,
    *,
    fault: CaseFault | None = None,
    send: bool = True,
    let_review_expire: bool = False,
) -> tuple[list[ReadableSpan], list[ReadableLogRecord]]:
    faults = StaticFaultRegistry({case_id: fault} if fault else None)
    agents = build_test_agents(ScriptedExtraction(), ScriptedAssessment(), faults)
    with captured_spans() as spans, captured_logs() as logs:
        async with time_skipping_env() as env, create_worker(env.client, TASK_QUEUE, agents):
            handle = await start_case(env.client, TASK_QUEUE, case_input(case_id, fault=fault))
            if send:
                await send_documents(handle, required_documents())
            if fault == CaseFault.tight_budget and not let_review_expire:
                await wait_for_status(handle, CaseStatus.awaiting_review)
                await handle.terminate()
            else:
                await handle.result()
        return list(spans.get_finished_spans()), [
            record
            for record in logs.get_finished_logs()
            if log_attribute(record, CASE_ID_ATTRIBUTE) == case_id
        ]


def _lines(records: list[ReadableLogRecord], body: str) -> list[ReadableLogRecord]:
    return [record for record in records if log_body(record) == body]


def _line(records: list[ReadableLogRecord], body: str) -> ReadableLogRecord:
    (record,) = _lines(records, body)
    return record


def _sits_on(record: ReadableLogRecord, span: ReadableSpan) -> bool:
    return (record.log_record.trace_id, record.log_record.span_id) == (
        trace_id(span),
        span_id(span),
    )


def _severity(record: ReadableLogRecord) -> str | None:
    return record.log_record.severity_text


async def test_workflow_lines_carry_the_span_they_were_written_under() -> None:
    spans, records = await _run_case("case-log-context")

    documents_complete = _line(records, "documents complete")
    decided = _line(records, "assessment decided approve")
    closed = _line(records, "case closed")

    assert _sits_on(documents_complete, only(spans, "kyc.await_documents"))
    assert _sits_on(decided, only(spans, "kyc.assess"))
    assert _sits_on(closed, only(spans, RUN_WORKFLOW))
    assert log_attribute(decided, ASSESSMENT_DECISION_ATTRIBUTE) == "approve"
    assert log_attribute(closed, OUTCOME_ATTRIBUTE) == CaseOutcome.approved.value
    assert {_severity(record) for record in (documents_complete, decided, closed)} == {"INFO"}


async def test_each_failing_sanctions_attempt_logs_an_error_on_its_run_activity_span() -> None:
    spans, records = await _run_case("case-log-sanctions-down", fault=CaseFault.sanctions_down)

    failed_attempts = [
        span
        for span in named(spans, FAILED_TOOL_ACTIVITY)
        if span.status.status_code == StatusCode.ERROR
    ]
    errors = _lines(records, "injected sanctions_down fault")

    assert len(failed_attempts) == 3
    assert sorted(log_attribute(record, ACTIVITY_ATTEMPT_ATTRIBUTE) for record in errors) == [
        1,
        2,
        3,
    ]
    assert {_severity(record) for record in errors} == {"ERROR"}
    for record in errors:
        assert sum(_sits_on(record, span) for span in failed_attempts) == 1


async def test_each_failing_model_attempt_logs_an_error_on_its_run_activity_span() -> None:
    spans, records = await _run_case(
        "case-log-model-unavailable", fault=CaseFault.model_unavailable
    )

    failed_attempts = [
        span
        for span in named(spans, FAILED_MODEL_ACTIVITY)
        if span.status.status_code == StatusCode.ERROR
    ]
    errors = _lines(records, "injected model_unavailable fault")

    assert len(failed_attempts) == 2
    assert sorted(log_attribute(record, ACTIVITY_ATTEMPT_ATTRIBUTE) for record in errors) == [1, 2]
    for record in errors:
        assert sum(_sits_on(record, span) for span in failed_attempts) == 1


async def test_budget_escalation_logs_the_failed_run_and_the_escalation_on_kyc_assess() -> None:
    spans, records = await _run_case("case-log-budget", fault=CaseFault.tight_budget)

    failed_run = _line(records, "agent run failed")
    escalated = _line(records, "case escalated for review")
    assess = only(spans, "kyc.assess")

    assert _severity(failed_run) == "ERROR"
    assert log_attribute(failed_run, "exception.type") == "UsageLimitExceeded"
    assert _severity(escalated) == "WARN"
    assert log_attribute(escalated, ESCALATION_REASON_ATTRIBUTE) == EscalationReason.budget.value
    assert _sits_on(failed_run, assess)
    assert _sits_on(escalated, assess)


async def test_document_deadline_logs_a_warning_on_the_wait_span() -> None:
    spans, records = await _run_case("case-log-expired", send=False)

    deadline = _line(records, "document deadline passed")
    closed = _line(records, "case closed")

    assert _severity(deadline) == "WARN"
    assert _sits_on(deadline, only(spans, "kyc.await_documents"))
    assert log_attribute(closed, OUTCOME_ATTRIBUTE) == CaseOutcome.expired.value


async def test_review_deadline_logs_a_warning_with_the_escalation_reason_on_the_wait_span() -> None:
    spans, records = await _run_case(
        "case-log-review-expired", fault=CaseFault.tight_budget, let_review_expire=True
    )

    deadline = _line(records, "review deadline passed")
    closed = _line(records, "case closed")

    assert _severity(deadline) == "WARN"
    assert log_attribute(deadline, ESCALATION_REASON_ATTRIBUTE) == EscalationReason.budget.value
    assert sum(_sits_on(deadline, span) for span in named(spans, "kyc.await_review")) == 1
    assert log_attribute(closed, OUTCOME_ATTRIBUTE) == CaseOutcome.expired.value
