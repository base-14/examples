"""Telemetry across durable execution: arrival links, prompt versions and worker handoff."""

import asyncio
import json
from collections import Counter
from typing import Any

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import ReadableSpan
from temporalio.api.enums.v1 import EventType
from temporalio.client import WorkflowHandle

from kyc_onboarding.agents import PROMPT_VERSION_METADATA_KEY
from kyc_onboarding.attributes import CASE_ID_ATTRIBUTE, OUTCOME_ATTRIBUTE
from kyc_onboarding.models import (
    CaseOutcome,
    CaseStatus,
    EscalateDecision,
    ReviewDecision,
    RiskLevel,
)
from kyc_onboarding.worker import create_worker
from kyc_onboarding.workflows import KycOnboardingWorkflow
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


TASK_QUEUE = "kyc-telemetry-test"
WAIT_SPANS = ("kyc.await_documents", "kyc.assess", "kyc.await_review")
ONE_PER_CASE_SPANS = (
    "RunWorkflow:KycOnboardingWorkflow",
    "kyc.await_documents",
    "kyc.assess",
    "kyc.await_review",
    "kyc.review_received",
    "HandleUpdate:submit_review",
    "invoke_agent kyc-assessment",
    "execute_tool screen_sanctions",
)
ESCALATE = EscalateDecision(risk_level=RiskLevel.medium, reasons=["partial sanctions match"])
REVIEW = ReviewDecision(decision="approve", reviewer="r.okafor")

pytestmark = pytest.mark.usefixtures("sanctions_clear")


def _linked_span_ids(span: ReadableSpan) -> list[int]:
    return [link.context.span_id for link in span.links]


async def _wait_for_review_timer(handle: WorkflowHandle[Any, Any]) -> None:
    """Reads history, since a query to a cache-less worker can be dropped on eviction."""
    async with asyncio.timeout(10):
        while True:
            events = (await handle.fetch_history()).events
            assessed = any(
                e.event_type == EventType.EVENT_TYPE_ACTIVITY_TASK_COMPLETED for e in events
            )
            if assessed and events[-1].event_type == EventType.EVENT_TYPE_TIMER_STARTED:
                return
            await asyncio.sleep(0.05)


async def test_arrival_spans_link_to_the_signal_and_update_handler_spans() -> None:
    agents = build_test_agents(ScriptedExtraction(), ScriptedAssessment(decisions=[ESCALATE]))
    with captured_spans() as exporter:
        async with time_skipping_env() as env, create_worker(env.client, TASK_QUEUE, agents):
            handle = await start_case(env.client, TASK_QUEUE, case_input("case-links"))
            await send_documents(handle, required_documents())
            await wait_for_status(handle, CaseStatus.awaiting_review)
            await handle.execute_update(KycOnboardingWorkflow.submit_review, REVIEW)
            await handle.result()
        spans = list(exporter.get_finished_spans())

    handle_signal_ids = {span_id(s) for s in named(spans, "HandleSignal:submit_document")}
    document_links = [_linked_span_ids(span) for span in named(spans, "kyc.document_received")]
    assert len(handle_signal_ids) == 2
    assert sorted(link for links in document_links for link in links) == sorted(handle_signal_ids)

    handle_update = only(spans, "HandleUpdate:submit_review")
    review_received = only(spans, "kyc.review_received")
    assert _linked_span_ids(review_received) == [span_id(handle_update)]
    assert trace_id(handle_update) != trace_id(review_received)


async def test_one_trace_survives_a_cache_less_worker_handoff() -> None:
    """Both workers run cache-less; the test server routes a cached run to the stopped worker."""
    tracer = trace.get_tracer(__name__)
    agents = build_test_agents(ScriptedExtraction(), ScriptedAssessment(decisions=[ESCALATE]))
    with captured_spans() as exporter, captured_logs() as log_exporter:
        async with time_skipping_env() as env:
            async with create_worker(env.client, TASK_QUEUE, agents, max_cached_workflows=0):
                with tracer.start_as_current_span("POST /cases") as request_span:
                    handle = await start_case(env.client, TASK_QUEUE, case_input("case-restart"))
                await send_documents(handle, required_documents())
                await _wait_for_review_timer(handle)

            async with create_worker(env.client, TASK_QUEUE, agents, max_cached_workflows=0):
                await handle.execute_update(KycOnboardingWorkflow.submit_review, REVIEW)
                result = await handle.result()
        spans = list(exporter.get_finished_spans())
        workflow_lines = Counter(
            log_body(record)
            for record in log_exporter.get_finished_logs()
            if record.instrumentation_scope is not None
            and record.instrumentation_scope.name == "temporalio.workflow"
            and log_attribute(record, CASE_ID_ATTRIBUTE) == "case-restart"
        )

    assert result.outcome == CaseOutcome.approved
    assert workflow_lines == {
        "documents complete": 1,
        "assessment decided escalate": 1,
        "case escalated for review": 1,
        "case closed": 1,
    }
    case_trace_id = request_span.get_span_context().trace_id
    case_spans = [span for span in spans if trace_id(span) == case_trace_id]
    all_names = Counter(span.name for span in spans)
    case_names = Counter(span.name for span in case_spans)

    assert len({span_id(span) for span in spans}) == len(spans)
    for name in ONE_PER_CASE_SPANS:
        assert all_names[name] == 1, name
    for name in (
        "kyc.document_received",
        "HandleSignal:submit_document",
        "invoke_agent kyc-extraction",
    ):
        assert all_names[name] == 2, name
    for name in (*WAIT_SPANS, "RunWorkflow:KycOnboardingWorkflow", "kyc.document_received"):
        assert case_names[name] == all_names[name], name
    assert case_names["invoke_agent kyc-extraction"] == 2
    assert case_names["invoke_agent kyc-assessment"] == 1

    run_workflow = only(case_spans, "RunWorkflow:KycOnboardingWorkflow")
    await_review = only(case_spans, "kyc.await_review")
    assert await_review.parent is not None
    assert await_review.parent.span_id == span_id(run_workflow)
    assert run_workflow.attributes is not None
    assert run_workflow.attributes[OUTCOME_ATTRIBUTE] == CaseOutcome.approved.value

    handle_signal_ids = sorted(span_id(s) for s in named(spans, "HandleSignal:submit_document"))
    document_links = sorted(
        link
        for received in named(case_spans, "kyc.document_received")
        for link in _linked_span_ids(received)
    )
    assert document_links == handle_signal_ids
    review_link = _linked_span_ids(only(case_spans, "kyc.review_received"))
    assert review_link == [span_id(only(spans, "HandleUpdate:submit_review"))]


async def test_every_agent_run_carries_the_case_prompt_version() -> None:
    agents = build_test_agents(ScriptedExtraction(), ScriptedAssessment())
    with captured_spans() as exporter:
        async with time_skipping_env() as env, create_worker(env.client, TASK_QUEUE, agents):
            handle = await start_case(env.client, TASK_QUEUE, case_input("case-prompt-metadata"))
            await send_documents(handle, required_documents())
            await handle.result()
        spans = list(exporter.get_finished_spans())

    runs = [span for span in spans if span.name.startswith("invoke_agent ")]
    by_agent = Counter(span.name for span in runs)
    assert by_agent == {"invoke_agent kyc-extraction": 2, "invoke_agent kyc-assessment": 1}
    versions = {
        "invoke_agent kyc-extraction": EXTRACTION_PROMPT_VERSION,
        "invoke_agent kyc-assessment": ASSESSMENT_PROMPT_VERSION,
    }
    for run in runs:
        assert run.attributes is not None
        metadata = json.loads(str(run.attributes["metadata"]))
        assert metadata == {PROMPT_VERSION_METADATA_KEY: versions[run.name]}, run.name
