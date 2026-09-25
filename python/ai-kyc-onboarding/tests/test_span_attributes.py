"""Business and GenAI attributes on the case's spans, read from an in-memory span exporter."""

from collections.abc import Sequence

import pytest
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode

from kyc_onboarding.agents import StaticFaultRegistry
from kyc_onboarding.attributes import (
    ASSESSMENT_DECISION_ATTRIBUTE,
    CASE_ID_ATTRIBUTE,
    DOCUMENTS_TO_RESEND_ATTRIBUTE,
    ESCALATION_REASON_ATTRIBUTE,
    MISSING_DOCUMENTS_ATTRIBUTE,
    PROMPT_VERSION_ATTRIBUTE,
    RISK_LEVEL_ATTRIBUTE,
    SANCTIONS_RESULT_ATTRIBUTE,
    SANCTIONS_SCORE_ATTRIBUTE,
)
from kyc_onboarding.models import (
    ApproveDecision,
    AssessmentDecision,
    CaseFault,
    CaseStatus,
    DocumentType,
    EscalateDecision,
    RequestResubmissionDecision,
    RiskLevel,
)
from kyc_onboarding.telemetry import ERROR_TYPE_ATTRIBUTE, CostAndErrorAttributingSpanExporter
from kyc_onboarding.tools import SanctionsScreeningResult
from kyc_onboarding.worker import create_worker
from tests._telemetry_support import (
    captured_logs,
    captured_spans,
    log_attribute,
    log_body,
    named,
    span_id,
)
from tests._workflow_support import (
    ASSESSMENT_PROMPT_VERSION,
    EXTRACTION_PROMPT_VERSION,
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


TASK_QUEUE = "kyc-span-attributes-test"
SANCTIONS_TOOL_ACTIVITY = "RunActivity:agent__kyc-assessment__toolset__<agent>__call_tool"
NAMESAKE = "Mario Gonzales"
ESCALATE = EscalateDecision(risk_level=RiskLevel.high, reasons=["partial sanctions match"])
RESEND_BOTH = RequestResubmissionDecision(
    reasons=["documents unreadable"],
    documents_to_resend=[DocumentType.proof_of_address, DocumentType.id],
)


async def _run_case(
    case_id: str,
    decisions: Sequence[AssessmentDecision] = (),
    *,
    fault: CaseFault | None = None,
    send: bool = True,
    resend_round: bool = False,
) -> list[ReadableSpan]:
    faults = StaticFaultRegistry({case_id: fault} if fault else None)
    assessment = ScriptedAssessment(decisions=decisions) if decisions else ScriptedAssessment()
    agents = build_test_agents(ScriptedExtraction(), assessment, faults)
    with captured_spans() as exporter:
        async with time_skipping_env() as env, create_worker(env.client, TASK_QUEUE, agents):
            handle = await start_case(env.client, TASK_QUEUE, case_input(case_id, fault=fault))
            if send:
                await send_documents(handle, required_documents())
            if resend_round:
                await wait_for_status(handle, CaseStatus.awaiting_documents, resubmission_round=1)
                await send_documents(handle, required_documents())
            if fault == CaseFault.tight_budget or (
                decisions and isinstance(decisions[-1], EscalateDecision)
            ):
                await wait_for_status(handle, CaseStatus.awaiting_review)
                await handle.terminate()
            else:
                await handle.result()
        return list(exporter.get_finished_spans())


def _attributes(span: ReadableSpan) -> dict[str, object]:
    return dict(span.attributes or {})


def _sanctions_attempts(spans: list[ReadableSpan]) -> list[ReadableSpan]:
    """The tool activity attempts under `execute_tool screen_sanctions`, whose `RunActivity`
    span is the current span inside the tool."""
    parents = {span_id(span): span for span in spans}

    def parent(span: ReadableSpan) -> ReadableSpan | None:
        return parents.get(span.parent.span_id) if span.parent else None

    return [
        span
        for span in named(spans, SANCTIONS_TOOL_ACTIVITY)
        if (start := parent(span)) is not None
        and (tool := parent(start)) is not None
        and tool.name == "execute_tool screen_sanctions"
    ]


def _genai_spans(spans: list[ReadableSpan]) -> list[ReadableSpan]:
    return [
        span
        for span in spans
        if _attributes(span).get("gen_ai.operation.name")
        in ("invoke_agent", "chat", "execute_tool")
    ]


@pytest.fixture
def sanctions_near_match(monkeypatch: pytest.MonkeyPatch) -> None:
    def screen(name: str, dsn: str) -> SanctionsScreeningResult:
        return SanctionsScreeningResult(result="partial", matched_entry=NAMESAKE, score=0.62)

    monkeypatch.setattr("kyc_onboarding.agents.tools._screen_sanctions", screen)


@pytest.mark.usefixtures("sanctions_clear")
async def test_an_approve_decision_is_on_the_assess_span() -> None:
    spans = await _run_case("case-attrs-approve")

    (assess,) = named(spans, "kyc.assess")
    assert _attributes(assess)[ASSESSMENT_DECISION_ATTRIBUTE] == "approve"
    assert ESCALATION_REASON_ATTRIBUTE not in _attributes(assess)
    assert RISK_LEVEL_ATTRIBUTE not in _attributes(assess)


@pytest.mark.usefixtures("sanctions_clear")
async def test_an_escalate_decision_puts_risk_level_and_reason_on_the_assess_span() -> None:
    case_id = "case-attrs-escalate"
    with captured_logs() as log_exporter:
        spans = await _run_case(case_id, [ESCALATE])
        escalation_lines = [
            record
            for record in log_exporter.get_finished_logs()
            if log_attribute(record, CASE_ID_ATTRIBUTE) == case_id
            and log_body(record) == "case escalated for review"
        ]

    (assess,) = named(spans, "kyc.assess")
    attributes = _attributes(assess)
    assert attributes[ASSESSMENT_DECISION_ATTRIBUTE] == "escalate"
    assert attributes[RISK_LEVEL_ATTRIBUTE] == "high"
    assert attributes[ESCALATION_REASON_ATTRIBUTE] == "risk"
    assert len(escalation_lines) == 1
    assert log_attribute(escalation_lines[0], ESCALATION_REASON_ATTRIBUTE) == "risk"


@pytest.mark.usefixtures("sanctions_clear")
async def test_a_resubmission_decision_lists_the_documents_to_resend_sorted() -> None:
    spans = await _run_case(
        "case-attrs-resend", [RESEND_BOTH, ApproveDecision()], resend_round=True
    )

    first, second = named(spans, "kyc.assess")
    assert _attributes(first)[ASSESSMENT_DECISION_ATTRIBUTE] == "request_resubmission"
    assert _attributes(first)[DOCUMENTS_TO_RESEND_ATTRIBUTE] == ("id", "proof_of_address")
    assert DOCUMENTS_TO_RESEND_ATTRIBUTE not in _attributes(second)


@pytest.mark.usefixtures("sanctions_clear")
async def test_the_document_deadline_puts_the_missing_documents_on_the_wait_span() -> None:
    spans = await _run_case("case-attrs-expired", send=False)

    (waiting,) = named(spans, "kyc.await_documents")
    assert _attributes(waiting)[MISSING_DOCUMENTS_ATTRIBUTE] == ("id", "proof_of_address")


@pytest.mark.usefixtures("sanctions_clear")
async def test_documents_arriving_in_time_leave_no_missing_documents_on_the_wait_span() -> None:
    spans = await _run_case("case-attrs-complete")

    (waiting,) = named(spans, "kyc.await_documents")
    assert MISSING_DOCUMENTS_ATTRIBUTE not in _attributes(waiting)


@pytest.mark.usefixtures("sanctions_clear")
async def test_a_clear_screening_is_on_the_tool_activity_span_without_a_score() -> None:
    spans = await _run_case("case-attrs-clear")

    (tool,) = _sanctions_attempts(spans)
    attributes = _attributes(tool)
    assert attributes[SANCTIONS_RESULT_ATTRIBUTE] == "clear"
    assert SANCTIONS_SCORE_ATTRIBUTE not in attributes


@pytest.mark.usefixtures("sanctions_near_match")
async def test_a_near_match_carries_its_score_but_never_the_matched_name() -> None:
    spans = await _run_case("case-attrs-near-match", [ESCALATE])

    (tool,) = _sanctions_attempts(spans)
    assert _attributes(tool)[SANCTIONS_RESULT_ATTRIBUTE] == "near_match"
    assert _attributes(tool)[SANCTIONS_SCORE_ATTRIBUTE] == 0.62
    assert NAMESAKE not in str(_attributes(tool))


@pytest.mark.usefixtures("sanctions_clear")
async def test_a_failed_screening_attempt_carries_result_error() -> None:
    spans = await _run_case("case-attrs-sanctions-down", fault=CaseFault.sanctions_down)

    attempts = _sanctions_attempts(spans)
    failed = [span for span in attempts if span.status.status_code == StatusCode.ERROR]
    succeeded = [span for span in attempts if span.status.status_code != StatusCode.ERROR]
    assert failed
    assert {_attributes(span)[SANCTIONS_RESULT_ATTRIBUTE] for span in failed} == {"error"}
    assert [_attributes(span)[SANCTIONS_RESULT_ATTRIBUTE] for span in succeeded] == ["clear"]


@pytest.mark.usefixtures("sanctions_clear")
async def test_every_genai_span_of_the_case_carries_the_case_id_as_conversation_id() -> None:
    case_id = "case-attrs-conversation"
    spans = await _run_case(case_id)

    genai = _genai_spans(spans)
    operations = {_attributes(span)["gen_ai.operation.name"] for span in genai}
    assert operations == {"invoke_agent", "chat", "execute_tool"}
    assert len(genai) > len({span.name for span in genai})
    assert [
        span.name for span in genai if _attributes(span).get("gen_ai.conversation.id") != case_id
    ] == []


@pytest.mark.usefixtures("sanctions_clear")
async def test_both_agents_describe_themselves_on_their_run_spans() -> None:
    spans = await _run_case("case-attrs-description")

    descriptions = {
        span.name: _attributes(span).get("gen_ai.agent.description")
        for span in spans
        if span.name.startswith("invoke_agent ")
    }
    assert set(descriptions) == {"invoke_agent kyc-extraction", "invoke_agent kyc-assessment"}
    assert all(isinstance(text, str) and text.endswith(".") for text in descriptions.values())


def _through_the_exporter(spans: list[ReadableSpan]) -> list[ReadableSpan]:
    exported = InMemorySpanExporter()
    CostAndErrorAttributingSpanExporter(exported).export(spans)
    return list(exported.get_finished_spans())


@pytest.mark.usefixtures("sanctions_clear")
async def test_the_exporter_puts_each_agent_run_prompt_version_on_its_run_span() -> None:
    spans = _through_the_exporter(await _run_case("case-attrs-prompt-version"))

    versions = {
        span.name: _attributes(span).get(PROMPT_VERSION_ATTRIBUTE)
        for span in spans
        if span.name.startswith("invoke_agent ")
    }
    assert versions == {
        "invoke_agent kyc-extraction": EXTRACTION_PROMPT_VERSION,
        "invoke_agent kyc-assessment": ASSESSMENT_PROMPT_VERSION,
    }


@pytest.mark.usefixtures("sanctions_clear")
async def test_the_exporter_types_the_error_on_a_run_stopped_by_the_budget() -> None:
    spans = _through_the_exporter(
        await _run_case("case-attrs-budget", fault=CaseFault.tight_budget)
    )

    (run,) = named(spans, "invoke_agent kyc-assessment")
    assert run.status.status_code == StatusCode.ERROR
    assert _attributes(run)[ERROR_TYPE_ATTRIBUTE] == "pydantic_ai.exceptions.UsageLimitExceeded"
