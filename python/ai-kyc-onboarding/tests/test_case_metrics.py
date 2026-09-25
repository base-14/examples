"""The workflow's application metrics, read from an in-memory reader.

Each metric moves once per event and does not count twice under replay.
"""

from datetime import timedelta

import pytest
from temporalio.worker import Replayer

from kyc_onboarding import case_metrics
from kyc_onboarding.attributes import (
    DOCUMENT_TYPE_ATTRIBUTE,
    ESCALATION_REASON_ATTRIBUTE,
    OUTCOME_ATTRIBUTE,
    REVIEW_DECISION_ATTRIBUTE,
)
from kyc_onboarding.models import (
    CaseFault,
    CaseOutcome,
    CaseStatus,
    DocumentType,
    EscalateDecision,
    EscalationReason,
    RequestResubmissionDecision,
    ReviewDecision,
    RiskLevel,
)
from kyc_onboarding.worker import create_worker
from kyc_onboarding.workflows import KycOnboardingWorkflow
from tests._telemetry_support import (
    captured_spans,
    collected_points,
    counter_value,
    histogram_count,
    metric_point,
    only,
    point_with,
    span_id,
    trace_id,
)
from tests._workflow_support import (
    REVIEW_DEADLINE,
    ScriptedAssessment,
    ScriptedExtraction,
    build_test_agents,
    case_input,
    client_plugins,
    document,
    required_documents,
    send_documents,
    start_case,
    time_skipping_env,
    wait_for_status,
)


TASK_QUEUE = "kyc-metrics-test"
RESEND_ADDRESS = RequestResubmissionDecision(
    reasons=["address on id does not match proof_of_address"],
    documents_to_resend=[DocumentType.proof_of_address],
)
ESCALATE = EscalateDecision(risk_level=RiskLevel.medium, reasons=["partial sanctions match"])
APPROVED = {OUTCOME_ATTRIBUTE: CaseOutcome.approved.value}
APPROVED_AFTER_RISK = {**APPROVED, ESCALATION_REASON_ATTRIBUTE: EscalationReason.risk.value}
EXPIRED_AFTER_BUDGET = {
    OUTCOME_ATTRIBUTE: CaseOutcome.expired.value,
    ESCALATION_REASON_ATTRIBUTE: EscalationReason.budget.value,
}
RESENT_ADDRESS = {DOCUMENT_TYPE_ATTRIBUTE: DocumentType.proof_of_address.value}
REVIEW_APPROVED = {REVIEW_DECISION_ATTRIBUTE: "approve"}
REVIEW_EXPIRED = {REVIEW_DECISION_ATTRIBUTE: "expired"}

pytestmark = pytest.mark.usefixtures("sanctions_clear")


def _workflow_metrics() -> dict[str, int]:
    return {
        "cases approved after risk": counter_value(case_metrics.CASES, APPROVED_AFTER_RISK),
        "case duration approved": histogram_count(case_metrics.CASE_DURATION, APPROVED),
        "resubmissions address": counter_value(case_metrics.RESUBMISSIONS, RESENT_ADDRESS),
        "review wait approved": histogram_count(case_metrics.REVIEW_WAIT, REVIEW_APPROVED),
    }


async def test_histograms_keep_an_exemplar_on_the_span_they_were_recorded_under() -> None:
    agents = build_test_agents(ScriptedExtraction(), ScriptedAssessment(decisions=[ESCALATE]))
    with captured_spans() as exporter:
        async with time_skipping_env() as env, create_worker(env.client, TASK_QUEUE, agents):
            handle = await start_case(env.client, TASK_QUEUE, case_input("case-exemplars"))
            await send_documents(handle, required_documents())
            await wait_for_status(handle, CaseStatus.awaiting_review)
            await handle.execute_update(
                KycOnboardingWorkflow.submit_review,
                ReviewDecision(decision="approve", reviewer="r.okafor"),
            )
            await handle.result()
        spans = list(exporter.get_finished_spans())
    run_workflow = only(spans, "RunWorkflow:KycOnboardingWorkflow")
    await_review = only(spans, "kyc.await_review")

    points = collected_points()
    duration = point_with(points[case_metrics.CASE_DURATION], APPROVED)
    review_wait = point_with(points[case_metrics.REVIEW_WAIT], REVIEW_APPROVED)

    assert duration is not None
    assert review_wait is not None
    assert (trace_id(run_workflow), span_id(run_workflow)) in {
        (exemplar.trace_id, exemplar.span_id) for exemplar in duration.exemplars
    }
    assert (trace_id(await_review), span_id(await_review)) in {
        (exemplar.trace_id, exemplar.span_id) for exemplar in review_wait.exemplars
    }


async def test_a_resubmitted_then_reviewed_case_moves_each_metric_once_despite_replay() -> None:
    before = _workflow_metrics()
    agents = build_test_agents(
        ScriptedExtraction(), ScriptedAssessment(decisions=[RESEND_ADDRESS, ESCALATE])
    )
    async with (
        time_skipping_env() as env,
        create_worker(env.client, TASK_QUEUE, agents, max_cached_workflows=0),
    ):
        handle = await start_case(env.client, TASK_QUEUE, case_input("case-metrics-replay"))
        await send_documents(handle, required_documents())
        await wait_for_status(handle, CaseStatus.awaiting_documents, resubmission_round=1)
        await send_documents(handle, [document(DocumentType.proof_of_address)])
        await wait_for_status(handle, CaseStatus.awaiting_review, resubmission_round=1)
        await handle.execute_update(
            KycOnboardingWorkflow.submit_review,
            ReviewDecision(decision="approve", reviewer="r.okafor"),
        )
        result = await handle.result()
        history = await handle.fetch_history()
    moved_once = {name: value + 1 for name, value in before.items()}

    assert result.outcome == CaseOutcome.approved
    assert _workflow_metrics() == moved_once

    await Replayer(workflows=[KycOnboardingWorkflow], plugins=client_plugins()).replay_workflow(
        history
    )
    assert _workflow_metrics() == moved_once


async def test_an_unreviewed_budget_escalation_records_the_expiry() -> None:
    cases_before = counter_value(case_metrics.CASES, EXPIRED_AFTER_BUDGET)
    waits_before = metric_point(case_metrics.REVIEW_WAIT, REVIEW_EXPIRED)
    agents = build_test_agents(ScriptedExtraction(), ScriptedAssessment())
    async with time_skipping_env() as env, create_worker(env.client, TASK_QUEUE, agents):
        handle = await start_case(
            env.client,
            TASK_QUEUE,
            case_input("case-metrics-budget", fault=CaseFault.tight_budget),
        )
        await send_documents(handle, required_documents())
        result = await handle.result()
    waits = metric_point(case_metrics.REVIEW_WAIT, REVIEW_EXPIRED)

    assert result.outcome == CaseOutcome.expired
    assert counter_value(case_metrics.CASES, EXPIRED_AFTER_BUDGET) == cases_before + 1
    assert waits is not None
    assert waits.count == (waits_before.count if waits_before else 0) + 1
    assert waits.sum - (waits_before.sum if waits_before else 0) == pytest.approx(
        REVIEW_DEADLINE / timedelta(seconds=1)
    )
