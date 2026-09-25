import asyncio

import pytest
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo
from temporalio.client import WorkflowExecutionStatus, WorkflowUpdateFailedError
from temporalio.exceptions import ApplicationError
from temporalio.service import RPCError, RPCStatusCode

from kyc_onboarding.agents import StaticFaultRegistry
from kyc_onboarding.agents.faults import (
    MODEL_UNAVAILABLE_MAX_ATTEMPT,
    SANCTIONS_DOWN_MAX_ATTEMPT,
)
from kyc_onboarding.models import (
    AccountType,
    ApproveDecision,
    CaseFault,
    CaseOutcome,
    CaseStatus,
    CaseStatusView,
    DocumentType,
    EscalateDecision,
    EscalationReason,
    ExtractedProofOfAddressFields,
    RequestResubmissionDecision,
    ReviewDecision,
    RiskLevel,
)
from kyc_onboarding.worker import create_worker
from kyc_onboarding.workflows import CASE_NOT_IN_REVIEW_ERROR, KycOnboardingWorkflow
from tests._workflow_support import (
    APPLICANT,
    ScriptedAssessment,
    ScriptedExtraction,
    build_test_agents,
    case_input,
    document,
    final_attempts,
    required_documents,
    send_documents,
    start_case,
    time_skipping_env,
    wait_for_status,
    wait_until,
    workflow_task_failures,
)


TASK_QUEUE = "kyc-workflow-test"

RESEND_ADDRESS = RequestResubmissionDecision(
    reasons=["address on id does not match proof_of_address"],
    documents_to_resend=[DocumentType.proof_of_address],
)
RESEND_EXPIRED_ID = RequestResubmissionDecision(
    reasons=["id expired"], documents_to_resend=[DocumentType.id]
)
PARTIAL_SANCTIONS_MATCH = EscalateDecision(
    risk_level=RiskLevel.medium, reasons=["partial sanctions match"]
)

pytestmark = pytest.mark.usefixtures("sanctions_clear")


async def test_case_models_cross_the_payload_converter_as_input_signal_update_and_query() -> None:
    agents = build_test_agents(
        ScriptedExtraction(), ScriptedAssessment(decisions=[PARTIAL_SANCTIONS_MATCH])
    )
    review = ReviewDecision(decision="approve", reviewer="r.okafor", note="match is a namesake")
    async with time_skipping_env() as env, create_worker(env.client, TASK_QUEUE, agents):
        handle = await start_case(env.client, TASK_QUEUE, case_input("case-payloads"))
        initial = await handle.query(KycOnboardingWorkflow.status)
        await send_documents(handle, required_documents())
        in_review = await wait_for_status(handle, CaseStatus.awaiting_review)
        after_review = await handle.execute_update(KycOnboardingWorkflow.submit_review, review)
        result = await handle.result()

    assert isinstance(initial, CaseStatusView)
    assert initial.missing_documents == [DocumentType.id, DocumentType.proof_of_address]
    assert in_review.decisions == [PARTIAL_SANCTIONS_MATCH]
    assert isinstance(after_review, CaseStatusView)
    assert after_review.review == review
    assert result == after_review
    assert result.outcome == CaseOutcome.approved


async def test_clean_documents_are_approved_without_review(sanctions_clear: list[str]) -> None:
    extraction = ScriptedExtraction()
    agents = build_test_agents(extraction, ScriptedAssessment())
    async with time_skipping_env() as env, create_worker(env.client, TASK_QUEUE, agents):
        handle = await start_case(env.client, TASK_QUEUE, case_input("case-auto-approved"))
        await send_documents(handle, required_documents())
        result = await handle.result()

    assert result.status == CaseStatus.approved
    assert result.outcome == CaseOutcome.approved
    assert result.escalation_reason is None
    assert result.review is None
    assert result.resubmission_round == 0
    assert result.decisions == [ApproveDecision()]
    assert sorted(extraction.calls) == [DocumentType.id, DocumentType.proof_of_address]
    assert sanctions_clear == [APPLICANT]


async def test_business_case_waits_for_the_registration_certificate() -> None:
    extraction = ScriptedExtraction()
    agents = build_test_agents(extraction, ScriptedAssessment())
    async with time_skipping_env() as env, create_worker(env.client, TASK_QUEUE, agents):
        handle = await start_case(
            env.client,
            TASK_QUEUE,
            case_input("case-business", account_type=AccountType.business),
        )
        await send_documents(handle, required_documents())
        waiting = await wait_until(
            handle,
            lambda view: view.missing_documents == [DocumentType.registration_certificate],
        )
        await send_documents(handle, [document(DocumentType.registration_certificate)])
        result = await handle.result()

    assert waiting.status == CaseStatus.awaiting_documents
    assert waiting.missing_documents == [DocumentType.registration_certificate]
    assert result.outcome == CaseOutcome.approved
    assert DocumentType.registration_certificate in extraction.calls


async def test_corrected_resubmission_is_approved_after_one_round() -> None:
    extraction = ScriptedExtraction()
    agents = build_test_agents(
        extraction, ScriptedAssessment(decisions=[RESEND_ADDRESS, ApproveDecision()])
    )
    async with time_skipping_env() as env, create_worker(env.client, TASK_QUEUE, agents):
        handle = await start_case(env.client, TASK_QUEUE, case_input("case-resubmission"))
        await send_documents(handle, required_documents())
        waiting = await wait_for_status(handle, CaseStatus.awaiting_documents, resubmission_round=1)
        await send_documents(handle, [document(DocumentType.proof_of_address)])
        result = await handle.result()

    assert waiting.missing_documents == [DocumentType.proof_of_address]
    assert result.outcome == CaseOutcome.approved
    assert result.resubmission_round == 1
    assert result.decisions == [RESEND_ADDRESS, ApproveDecision()]
    assert result.escalation_reason is None
    assert extraction.calls.count(DocumentType.id) == 1
    assert extraction.calls.count(DocumentType.proof_of_address) == 2


async def test_an_approval_after_a_missing_id_expiry_date_becomes_a_request_for_the_id() -> None:
    resend_id = RequestResubmissionDecision(
        reasons=["the ID's expiry date is missing"], documents_to_resend=[DocumentType.id]
    )
    assessment = ScriptedAssessment(
        decisions=[ApproveDecision(), resend_id],
        checks=[ToolCallPart(tool_name="check_expiry", args={"expiry_date": None})],
    )
    agents = build_test_agents(ScriptedExtraction(), assessment)
    async with time_skipping_env() as env, create_worker(env.client, TASK_QUEUE, agents):
        handle = await start_case(env.client, TASK_QUEUE, case_input("case-missing-expiry"))
        await send_documents(handle, required_documents())
        waiting = await wait_for_status(handle, CaseStatus.awaiting_documents, resubmission_round=1)

    assert waiting.missing_documents == [DocumentType.id]
    assert waiting.decisions == [resend_id]
    assert assessment.rounds == 2


async def test_third_resubmission_request_rejects_the_case_at_the_cap() -> None:
    agents = build_test_agents(
        ScriptedExtraction(), ScriptedAssessment(decisions=[RESEND_EXPIRED_ID])
    )
    async with time_skipping_env() as env, create_worker(env.client, TASK_QUEUE, agents):
        handle = await start_case(env.client, TASK_QUEUE, case_input("case-cap"))
        await send_documents(handle, required_documents())
        for resubmission_round in (1, 2):
            await wait_for_status(
                handle, CaseStatus.awaiting_documents, resubmission_round=resubmission_round
            )
            await send_documents(handle, [document(DocumentType.id)])
        result = await handle.result()

    assert result.outcome == CaseOutcome.rejected
    assert result.status == CaseStatus.rejected
    assert result.resubmission_round == 2
    assert result.decisions == [RESEND_EXPIRED_ID] * 3
    assert result.escalation_reason is None
    assert result.review is None


@pytest.mark.parametrize(
    ("decision", "outcome"),
    [("approve", CaseOutcome.approved), ("reject", CaseOutcome.rejected)],
)
async def test_reviewer_decides_an_escalated_risk_case(decision: str, outcome: CaseOutcome) -> None:
    agents = build_test_agents(
        ScriptedExtraction(), ScriptedAssessment(decisions=[PARTIAL_SANCTIONS_MATCH])
    )
    review = ReviewDecision.model_validate({"decision": decision, "reviewer": "r.okafor"})
    async with time_skipping_env() as env, create_worker(env.client, TASK_QUEUE, agents):
        handle = await start_case(env.client, TASK_QUEUE, case_input(f"case-review-{decision}"))
        await send_documents(handle, required_documents())
        in_review = await wait_for_status(handle, CaseStatus.awaiting_review)
        await handle.execute_update(KycOnboardingWorkflow.submit_review, review)
        result = await handle.result()

    assert in_review.escalation_reason == EscalationReason.risk
    assert result.outcome == outcome
    assert result.escalation_reason == EscalationReason.risk
    assert result.review == review


async def test_case_expires_when_no_documents_arrive_before_the_deadline() -> None:
    extraction = ScriptedExtraction()
    agents = build_test_agents(extraction, ScriptedAssessment())
    async with time_skipping_env() as env, create_worker(env.client, TASK_QUEUE, agents):
        handle = await start_case(env.client, TASK_QUEUE, case_input("case-expired"))
        result = await handle.result()

    assert result.outcome == CaseOutcome.expired
    assert result.status == CaseStatus.expired
    assert result.missing_documents == [DocumentType.id, DocumentType.proof_of_address]
    assert extraction.calls == []


async def test_case_expires_when_the_document_set_stays_incomplete() -> None:
    agents = build_test_agents(ScriptedExtraction(), ScriptedAssessment())
    async with time_skipping_env() as env, create_worker(env.client, TASK_QUEUE, agents):
        handle = await start_case(env.client, TASK_QUEUE, case_input("case-partial-expired"))
        await send_documents(handle, [document(DocumentType.id)])
        result = await handle.result()

    assert result.outcome == CaseOutcome.expired
    assert result.missing_documents == [DocumentType.proof_of_address]


async def test_case_expires_when_the_reviewer_does_not_decide_in_time() -> None:
    agents = build_test_agents(
        ScriptedExtraction(), ScriptedAssessment(decisions=[PARTIAL_SANCTIONS_MATCH])
    )
    async with time_skipping_env() as env, create_worker(env.client, TASK_QUEUE, agents):
        handle = await start_case(env.client, TASK_QUEUE, case_input("case-review-expired"))
        await send_documents(handle, required_documents())
        result = await handle.result()

    assert result.outcome == CaseOutcome.expired
    assert result.escalation_reason == EscalationReason.risk
    assert result.review is None


async def test_review_is_refused_while_the_case_is_not_awaiting_review() -> None:
    agents = build_test_agents(ScriptedExtraction(), ScriptedAssessment())
    review = ReviewDecision(decision="approve", reviewer="r.okafor")
    async with time_skipping_env() as env, create_worker(env.client, TASK_QUEUE, agents):
        handle = await start_case(env.client, TASK_QUEUE, case_input("case-review-refused"))
        with pytest.raises(WorkflowUpdateFailedError) as refused:
            await handle.execute_update(KycOnboardingWorkflow.submit_review, review)
        status = await handle.query(KycOnboardingWorkflow.status)
        await send_documents(handle, required_documents())
        await handle.result()

    assert isinstance(refused.value.cause, ApplicationError)
    assert refused.value.cause.type == CASE_NOT_IN_REVIEW_ERROR
    assert status.status == CaseStatus.awaiting_documents
    assert status.review is None


async def test_second_review_is_refused_while_the_first_is_pending() -> None:
    agents = build_test_agents(
        ScriptedExtraction(), ScriptedAssessment(decisions=[PARTIAL_SANCTIONS_MATCH])
    )
    approve = ReviewDecision(decision="approve", reviewer="r.okafor")
    reject = ReviewDecision(decision="reject", reviewer="a.lindqvist")
    async with time_skipping_env() as env, create_worker(env.client, TASK_QUEUE, agents):
        handle = await start_case(env.client, TASK_QUEUE, case_input("case-review-pending"))
        await send_documents(handle, required_documents())
        await wait_for_status(handle, CaseStatus.awaiting_review)
        outcomes = await asyncio.gather(
            handle.execute_update(KycOnboardingWorkflow.submit_review, approve),
            handle.execute_update(KycOnboardingWorkflow.submit_review, reject),
            return_exceptions=True,
        )
        result = await handle.result()

    accepted = [outcome for outcome in outcomes if isinstance(outcome, CaseStatusView)]
    refused = [outcome for outcome in outcomes if isinstance(outcome, BaseException)]
    assert len(accepted) == 1
    assert len(refused) == 1
    assert isinstance(refused[0], WorkflowUpdateFailedError)
    assert isinstance(refused[0].cause, ApplicationError)
    assert refused[0].cause.type == CASE_NOT_IN_REVIEW_ERROR
    assert result.review == accepted[0].review


async def test_review_is_refused_once_the_case_is_closed() -> None:
    agents = build_test_agents(ScriptedExtraction(), ScriptedAssessment())
    review = ReviewDecision(decision="reject", reviewer="r.okafor")
    async with time_skipping_env() as env, create_worker(env.client, TASK_QUEUE, agents):
        handle = await start_case(env.client, TASK_QUEUE, case_input("case-review-closed"))
        await send_documents(handle, required_documents())
        result = await handle.result()
        with pytest.raises(RPCError) as refused:
            await handle.execute_update(KycOnboardingWorkflow.submit_review, review)

    assert result.outcome == CaseOutcome.approved
    assert refused.value.status == RPCStatusCode.NOT_FOUND


async def test_model_unavailable_fails_only_the_first_model_activity_then_approves() -> None:
    faults = StaticFaultRegistry({"case-model-unavailable": CaseFault.model_unavailable})
    agents = build_test_agents(ScriptedExtraction(), ScriptedAssessment(), faults)
    async with time_skipping_env() as env, create_worker(env.client, TASK_QUEUE, agents):
        handle = await start_case(
            env.client,
            TASK_QUEUE,
            case_input("case-model-unavailable", fault=CaseFault.model_unavailable),
        )
        await send_documents(handle, required_documents())
        result = await handle.result()
        attempts = await final_attempts(handle)

    model_attempts = [attempt for name, attempt in attempts if name.endswith("__model_request")]
    assert result.outcome == CaseOutcome.approved
    assert result.escalation_reason is None
    assert model_attempts == [MODEL_UNAVAILABLE_MAX_ATTEMPT + 1, 1, 1, 1]


async def test_sanctions_down_retries_the_tool_activity_then_approves(
    sanctions_clear: list[str],
) -> None:
    agents = build_test_agents(ScriptedExtraction(), ScriptedAssessment())
    async with time_skipping_env() as env, create_worker(env.client, TASK_QUEUE, agents):
        handle = await start_case(
            env.client,
            TASK_QUEUE,
            case_input("case-sanctions-down", fault=CaseFault.sanctions_down),
        )
        await send_documents(handle, required_documents())
        result = await handle.result()
        attempts = await final_attempts(handle)

    tool_attempts = [attempt for name, attempt in attempts if name.endswith("__call_tool")]
    assert result.outcome == CaseOutcome.approved
    assert result.escalation_reason is None
    assert sanctions_clear == [APPLICANT]
    assert sorted(tool_attempts) == [1, 1, SANCTIONS_DOWN_MAX_ATTEMPT + 1]


async def test_bad_output_is_retried_once_by_the_agent_then_approves() -> None:
    extraction = ScriptedExtraction()
    faults = StaticFaultRegistry({"case-bad-output": CaseFault.bad_output})
    agents = build_test_agents(extraction, ScriptedAssessment(), faults)
    async with time_skipping_env() as env, create_worker(env.client, TASK_QUEUE, agents):
        handle = await start_case(
            env.client, TASK_QUEUE, case_input("case-bad-output", fault=CaseFault.bad_output)
        )
        await send_documents(handle, required_documents())
        result = await handle.result()

    assert result.outcome == CaseOutcome.approved
    assert len(extraction.calls) == len(required_documents()) + 1


async def test_tight_budget_escalates_with_reason_budget() -> None:
    agents = build_test_agents(ScriptedExtraction(), ScriptedAssessment())
    async with time_skipping_env() as env, create_worker(env.client, TASK_QUEUE, agents):
        handle = await start_case(
            env.client,
            TASK_QUEUE,
            case_input("case-tight-budget", fault=CaseFault.tight_budget),
        )
        await send_documents(handle, required_documents())
        in_review = await wait_for_status(handle, CaseStatus.awaiting_review)
        await handle.execute_update(
            KycOnboardingWorkflow.submit_review,
            ReviewDecision(decision="approve", reviewer="r.okafor"),
        )
        result = await handle.result()

    assert in_review.escalation_reason == EscalationReason.budget
    assert in_review.decisions == []
    assert result.outcome == CaseOutcome.approved
    assert result.escalation_reason == EscalationReason.budget


async def test_case_budget_is_summed_across_agent_runs() -> None:
    extraction = ScriptedExtraction()
    agents = build_test_agents(extraction, ScriptedAssessment())
    async with time_skipping_env() as env, create_worker(env.client, TASK_QUEUE, agents):
        handle = await start_case(
            env.client, TASK_QUEUE, case_input("case-budget", request_budget=3)
        )
        await send_documents(handle, required_documents())
        in_review = await wait_for_status(handle, CaseStatus.awaiting_review)
        await handle.result()

    assert len(extraction.calls) == 2
    assert in_review.escalation_reason == EscalationReason.budget


async def test_resend_request_naming_no_documents_escalates_with_reason_invalid_output() -> None:
    resend_nothing = RequestResubmissionDecision(
        reasons=["something is off"], documents_to_resend=[]
    )
    agents = build_test_agents(ScriptedExtraction(), ScriptedAssessment(decisions=[resend_nothing]))
    async with time_skipping_env() as env, create_worker(env.client, TASK_QUEUE, agents):
        handle = await start_case(env.client, TASK_QUEUE, case_input("case-resend-nothing"))
        await send_documents(handle, required_documents())
        in_review = await wait_for_status(handle, CaseStatus.awaiting_review)
        await handle.execute_update(
            KycOnboardingWorkflow.submit_review,
            ReviewDecision(decision="reject", reviewer="r.okafor"),
        )
        result = await handle.result()

    assert in_review.escalation_reason == EscalationReason.invalid_output
    assert in_review.resubmission_round == 0
    assert in_review.decisions == [resend_nothing]
    assert result.outcome == CaseOutcome.rejected


async def test_case_waits_for_a_worker_with_its_prompt_versions() -> None:
    agents = build_test_agents(ScriptedExtraction(), ScriptedAssessment())
    case = case_input("case-prompt-mismatch").model_copy(update={"assessment_prompt_version": "v9"})
    with workflow_task_failures() as failures:
        async with time_skipping_env() as env, create_worker(env.client, TASK_QUEUE, agents):
            handle = await start_case(env.client, TASK_QUEUE, case)
            await send_documents(handle, required_documents())
            failure = await failures.first()
            description = await handle.describe()
            await handle.terminate()

    assert "case needs prompt versions ('v1', 'v9'), this worker loaded ('v1', 'v3')" in failure
    assert description.status == WorkflowExecutionStatus.RUNNING


async def test_model_failure_after_retries_escalates_with_reason_agent_error() -> None:
    def unreachable_model(*_: object) -> ModelResponse:
        raise ConnectionError("ollama unreachable")

    agents = build_test_agents(ScriptedExtraction(), unreachable_model)
    async with time_skipping_env() as env, create_worker(env.client, TASK_QUEUE, agents):
        handle = await start_case(env.client, TASK_QUEUE, case_input("case-agent-error"))
        await send_documents(handle, required_documents())
        result = await handle.result()

    assert result.escalation_reason == EscalationReason.agent_error
    assert result.outcome == CaseOutcome.expired


async def test_output_that_never_validates_escalates_with_reason_invalid_output() -> None:
    def malformed_extraction(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        tool_name = info.output_tools[0].name
        return ModelResponse(parts=[ToolCallPart(tool_name=tool_name, args={})])

    agents = build_test_agents(malformed_extraction, ScriptedAssessment())
    async with time_skipping_env() as env, create_worker(env.client, TASK_QUEUE, agents):
        handle = await start_case(env.client, TASK_QUEUE, case_input("case-invalid-output"))
        await send_documents(handle, required_documents())
        result = await handle.result()

    assert result.escalation_reason == EscalationReason.invalid_output
    assert result.decisions == []


async def test_fields_for_the_wrong_document_type_escalate_with_reason_invalid_output() -> None:
    extraction = ScriptedExtraction(
        fields_override={
            DocumentType.id: ExtractedProofOfAddressFields(
                account_holder=APPLICANT, address="14 Harbour Road, Cork"
            )
        }
    )
    agents = build_test_agents(extraction, ScriptedAssessment())
    async with time_skipping_env() as env, create_worker(env.client, TASK_QUEUE, agents):
        handle = await start_case(env.client, TASK_QUEUE, case_input("case-wrong-type"))
        await send_documents(handle, required_documents())
        result = await handle.result()

    assert result.escalation_reason == EscalationReason.invalid_output
