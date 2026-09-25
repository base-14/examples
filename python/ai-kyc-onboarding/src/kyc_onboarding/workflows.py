import json
import logging
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from opentelemetry import trace
from opentelemetry.trace import Link, Span, SpanContext
from temporalio import workflow
from temporalio.exceptions import ActivityError, ApplicationError


with workflow.unsafe.imports_passed_through():
    # Pydantic imports annotated_types lazily when it first decodes an activity result
    # inside the sandbox; loading it here keeps that import out of workflow execution.
    import annotated_types  # noqa: F401
    from pydantic_ai import UsageLimits
    from pydantic_ai.exceptions import AgentRunError, UnexpectedModelBehavior, UsageLimitExceeded
    from pydantic_ai.usage import RunUsage

    from kyc_onboarding import case_metrics
    from kyc_onboarding.agents.deps import AssessmentDeps
    from kyc_onboarding.agents.prompts import PROMPT_VERSION_METADATA_KEY
    from kyc_onboarding.case_agents import CaseAgents, installed_case_agents
    from kyc_onboarding.models import (
        ApproveDecision,
        AssessmentDecision,
        Case,
        CaseFault,
        CaseInput,
        CaseOutcome,
        CaseStatus,
        CaseStatusView,
        DocumentType,
        EscalateDecision,
        EscalationReason,
        ExtractedDocument,
        ExtractedIdFields,
        ExtractedProofOfAddressFields,
        ExtractedRegistrationCertificateFields,
        RequestResubmissionDecision,
        ReviewDecision,
        SubmittedDocument,
    )

from kyc_onboarding.attributes import (
    ACCOUNT_TYPE_ATTRIBUTE,
    ASSESSMENT_DECISION_ATTRIBUTE,
    CASE_ID_ATTRIBUTE,
    DOCUMENT_TYPE_ATTRIBUTE,
    DOCUMENTS_TO_RESEND_ATTRIBUTE,
    ESCALATION_REASON_ATTRIBUTE,
    MISSING_DOCUMENTS_ATTRIBUTE,
    OUTCOME_ATTRIBUTE,
    PROMPT_VERSION_ATTRIBUTE,
    RESUBMISSION_ROUND_ATTRIBUTE,
    REVIEW_DECISION_ATTRIBUTE,
    RISK_LEVEL_ATTRIBUTE,
)


MAX_RESUBMISSION_ROUNDS = 2
EXTRACTION_RUN_REQUEST_LIMIT = 3
ASSESSMENT_RUN_REQUEST_LIMIT = 10
TIGHT_BUDGET_ASSESSMENT_REQUEST_LIMIT = 1

CASE_NOT_IN_REVIEW_ERROR = "CaseNotInReview"

_FIELDS_BY_DOCUMENT_TYPE: dict[DocumentType, type] = {
    DocumentType.id: ExtractedIdFields,
    DocumentType.proof_of_address: ExtractedProofOfAddressFields,
    DocumentType.registration_certificate: ExtractedRegistrationCertificateFields,
}


@dataclass(frozen=True)
class _DocumentArrival:
    document: SubmittedDocument
    sender_span: SpanContext


@dataclass(frozen=True)
class _ReviewArrival:
    review: ReviewDecision
    sender_span: SpanContext


class _ExtractedWrongDocumentType(Exception):
    pass


@workflow.defn(name="KycOnboardingWorkflow")
class KycOnboardingWorkflow:
    @workflow.init
    def __init__(self, case_input: CaseInput) -> None:
        self._input = case_input
        self._case = Case(
            case_id=case_input.case_id,
            name=case_input.name,
            country=case_input.country,
            account_type=case_input.account_type,
        )
        self._document_inbox: list[_DocumentArrival] = []
        self._review_arrival: _ReviewArrival | None = None
        self._extracted: dict[DocumentType, ExtractedDocument] = {}
        self._usage = RunUsage()

    @workflow.run
    async def run(self, case_input: CaseInput) -> CaseStatusView:
        case_span = trace.get_current_span()
        case_span.set_attributes(self._case_attributes())
        await self._decide_case()
        case_span.set_attributes(self._outcome_attributes())
        await workflow.wait_condition(workflow.all_handlers_finished)
        return CaseStatusView.of(self._case)

    @workflow.signal
    def submit_document(self, document: SubmittedDocument) -> None:
        self._document_inbox.append(
            _DocumentArrival(document, trace.get_current_span().get_span_context())
        )

    @workflow.update
    async def submit_review(self, review: ReviewDecision) -> CaseStatusView:
        if self._review_arrival is not None:
            raise _case_not_in_review(self._case.status)
        self._review_arrival = _ReviewArrival(review, trace.get_current_span().get_span_context())
        await workflow.wait_condition(lambda: self._case.outcome is not None)
        return CaseStatusView.of(self._case)

    @submit_review.validator
    def _accept_review_only_while_awaiting_one(self, review: ReviewDecision) -> None:
        if self._case.status != CaseStatus.awaiting_review or self._review_arrival is not None:
            raise _case_not_in_review(self._case.status)

    @workflow.query
    def status(self) -> CaseStatusView:
        return CaseStatusView.of(self._case)

    async def _decide_case(self) -> None:
        while True:
            if not await self._await_documents():
                self._close(CaseOutcome.expired)
                return
            assessment = await self._assess()
            match assessment:
                case ApproveDecision():
                    self._close(CaseOutcome.approved)
                    return
                case RequestResubmissionDecision():
                    if self._case.resubmission_round >= MAX_RESUBMISSION_ROUNDS:
                        self._close(CaseOutcome.rejected)
                        return
                    self._request_resubmission(assessment.documents_to_resend)
                case EscalateDecision():
                    self._case.escalation_reason = EscalationReason.risk
                    break
                case EscalationReason():
                    self._case.escalation_reason = assessment
                    break

        review = await self._await_review()
        if review is None:
            self._close(CaseOutcome.expired)
        elif review.decision == "approve":
            self._close(CaseOutcome.approved)
        else:
            self._close(CaseOutcome.rejected)

    async def _await_documents(self) -> bool:
        self._case.status = CaseStatus.awaiting_documents
        deadline = workflow.now() + self._input.document_deadline
        with _tracer().start_as_current_span(
            "kyc.await_documents", attributes=self._round_attributes()
        ):
            while True:
                self._receive_documents()
                if not self._case.missing_documents:
                    self._log(logging.INFO, "documents complete", self._round_attributes())
                    return True
                remaining = deadline - workflow.now()
                if remaining <= timedelta(0):
                    return self._document_deadline_passed()
                try:
                    await workflow.wait_condition(
                        lambda: bool(self._document_inbox), timeout=remaining
                    )
                except TimeoutError:
                    return self._document_deadline_passed()

    def _document_deadline_passed(self) -> bool:
        missing = [t.value for t in self._case.missing_documents]
        trace.get_current_span().set_attribute(MISSING_DOCUMENTS_ATTRIBUTE, missing)
        self._log(
            logging.WARNING, "document deadline passed", {MISSING_DOCUMENTS_ATTRIBUTE: missing}
        )
        return False

    def _receive_documents(self) -> None:
        while self._document_inbox:
            arrival = self._document_inbox.pop(0)
            document_type = arrival.document.document_type
            with _tracer().start_as_current_span(
                "kyc.document_received",
                links=[Link(arrival.sender_span)],
                attributes={
                    CASE_ID_ATTRIBUTE: self._case.case_id,
                    DOCUMENT_TYPE_ATTRIBUTE: document_type.value,
                },
            ):
                self._case.submitted_documents = [
                    document
                    for document in self._case.submitted_documents
                    if document.document_type != document_type
                ] + [arrival.document]
                self._extracted.pop(document_type, None)

    async def _assess(self) -> AssessmentDecision | EscalationReason:
        self._case.status = CaseStatus.assessing
        agents = self._agents_for_prompt_versions()
        with _tracer().start_as_current_span(
            "kyc.assess",
            attributes={
                **self._round_attributes(),
                PROMPT_VERSION_ATTRIBUTE: self._input.assessment_prompt_version,
            },
        ) as span:
            try:
                await self._extract_new_documents(agents)
                decision = await self._run_assessment(agents)
            except UsageLimitExceeded:
                return self._agent_run_failed(span, EscalationReason.budget)
            except UnexpectedModelBehavior, _ExtractedWrongDocumentType:
                return self._agent_run_failed(span, EscalationReason.invalid_output)
            except ActivityError, AgentRunError:
                return self._agent_run_failed(span, EscalationReason.agent_error)
            self._case.decisions.append(decision)
            span.set_attribute(ASSESSMENT_DECISION_ATTRIBUTE, decision.decision)
            self._log(
                logging.INFO,
                f"assessment decided {decision.decision}",
                {ASSESSMENT_DECISION_ATTRIBUTE: decision.decision},
            )
            if isinstance(decision, EscalateDecision):
                span.set_attribute(RISK_LEVEL_ATTRIBUTE, decision.risk_level.value)
                self._escalated(span, EscalationReason.risk)
            if isinstance(decision, RequestResubmissionDecision):
                if not decision.documents_to_resend:
                    return self._escalated(span, EscalationReason.invalid_output)
                span.set_attribute(
                    DOCUMENTS_TO_RESEND_ATTRIBUTE, _sorted_values(decision.documents_to_resend)
                )
            return decision

    def _agent_run_failed(self, span: Span, reason: EscalationReason) -> EscalationReason:
        self._log(logging.ERROR, "agent run failed", exc_info=True)
        return self._escalated(span, reason)

    def _escalated(self, span: Span, reason: EscalationReason) -> EscalationReason:
        span.set_attribute(ESCALATION_REASON_ATTRIBUTE, reason.value)
        self._log(
            logging.WARNING,
            "case escalated for review",
            {ESCALATION_REASON_ATTRIBUTE: reason.value},
        )
        return reason

    def _agents_for_prompt_versions(self) -> CaseAgents:
        agents = installed_case_agents()
        installed = (agents.extraction_prompt_version, agents.assessment_prompt_version)
        requested = (self._input.extraction_prompt_version, self._input.assessment_prompt_version)
        if installed != requested:
            raise RuntimeError(
                f"case needs prompt versions {requested}, this worker loaded {installed}"
            )
        return agents

    async def _extract_new_documents(self, agents: CaseAgents) -> None:
        for document in self._case.submitted_documents:
            if document.document_type in self._extracted:
                continue
            prompt = agents.extraction_prompt.user.format(
                document_type=document.document_type.value,
                document_text=document.raw_text,
            )
            result = await agents.extraction.run(
                prompt,
                usage=self._usage,
                usage_limits=self._usage_limits(EXTRACTION_RUN_REQUEST_LIMIT),
                metadata={PROMPT_VERSION_METADATA_KEY: self._input.extraction_prompt_version},
                conversation_id=self._case.case_id,
            )
            if not isinstance(result.output, _FIELDS_BY_DOCUMENT_TYPE[document.document_type]):
                raise _ExtractedWrongDocumentType(document.document_type)
            self._extracted[document.document_type] = ExtractedDocument(
                document_type=document.document_type, fields=result.output
            )

    async def _run_assessment(self, agents: CaseAgents) -> AssessmentDecision:
        extracted_documents = json.dumps(
            [
                self._extracted[document_type].model_dump(mode="json")
                for document_type in self._case.required_documents
            ],
            indent=2,
        )
        prompt = agents.assessment_prompt.user.format(
            case_id=self._case.case_id,
            account_type=self._case.account_type.value,
            extracted_documents=extracted_documents,
        )
        per_run_limit = (
            TIGHT_BUDGET_ASSESSMENT_REQUEST_LIMIT
            if self._input.fault == CaseFault.tight_budget
            else ASSESSMENT_RUN_REQUEST_LIMIT
        )
        result = await agents.assessment.run(
            prompt,
            deps=AssessmentDeps(
                dsn=agents.sanctions_dsn,
                reference_date=workflow.now().date(),
                fault=self._input.fault,
            ),
            usage=self._usage,
            usage_limits=self._usage_limits(per_run_limit),
            metadata={PROMPT_VERSION_METADATA_KEY: self._input.assessment_prompt_version},
            conversation_id=self._case.case_id,
        )
        return result.output

    def _usage_limits(self, per_run_request_limit: int) -> UsageLimits:
        return UsageLimits(
            request_limit=min(
                self._usage.requests + per_run_request_limit, self._input.request_budget
            )
        )

    def _request_resubmission(self, documents_to_resend: list[DocumentType]) -> None:
        self._case.resubmission_round += 1
        resend = set(documents_to_resend)
        self._log(
            logging.INFO,
            "resubmission requested",
            {
                RESUBMISSION_ROUND_ATTRIBUTE: self._case.resubmission_round,
                DOCUMENTS_TO_RESEND_ATTRIBUTE: _sorted_values(resend),
            },
        )
        for document_type in sorted(resend):
            case_metrics.record_resubmission(document_type.value)
        self._case.submitted_documents = [
            document
            for document in self._case.submitted_documents
            if document.document_type not in resend
        ]
        for document_type in resend:
            self._extracted.pop(document_type, None)

    async def _await_review(self) -> ReviewDecision | None:
        self._case.status = CaseStatus.awaiting_review
        waiting_since = workflow.now()
        with _tracer().start_as_current_span(
            "kyc.await_review",
            attributes={
                **self._round_attributes(),
                ESCALATION_REASON_ATTRIBUTE: str(self._case.escalation_reason),
            },
        ):
            try:
                await workflow.wait_condition(
                    lambda: self._review_arrival is not None,
                    timeout=self._input.review_deadline,
                )
            except TimeoutError:
                self._log(
                    logging.WARNING,
                    "review deadline passed",
                    {ESCALATION_REASON_ATTRIBUTE: str(self._case.escalation_reason)},
                )
                case_metrics.record_review_wait("expired", workflow.now() - waiting_since)
                return None
            arrival = self._review_arrival
            assert arrival is not None
            with _tracer().start_as_current_span(
                "kyc.review_received",
                links=[Link(arrival.sender_span)],
                attributes={
                    CASE_ID_ATTRIBUTE: self._case.case_id,
                    REVIEW_DECISION_ATTRIBUTE: arrival.review.decision,
                },
            ):
                self._case.review = arrival.review
            case_metrics.record_review_wait(arrival.review.decision, workflow.now() - waiting_since)
            return arrival.review

    def _close(self, outcome: CaseOutcome) -> None:
        self._case.outcome = outcome
        self._case.status = CaseStatus(outcome.value)
        escalation_reason = self._case.escalation_reason
        self._log(logging.INFO, "case closed", self._outcome_attributes())
        case_metrics.record_case_closed(
            outcome.value,
            escalation_reason.value if escalation_reason is not None else None,
            workflow.now() - workflow.info().start_time,
        )

    def _log(
        self,
        level: int,
        message: str,
        attributes: dict[str, Any] | None = None,
        *,
        exc_info: bool = False,
    ) -> None:
        workflow.logger.log(
            level,
            message,
            extra={CASE_ID_ATTRIBUTE: self._case.case_id, **(attributes or {})},
            exc_info=exc_info,
        )

    def _case_attributes(self) -> dict[str, str]:
        return {
            CASE_ID_ATTRIBUTE: self._case.case_id,
            ACCOUNT_TYPE_ATTRIBUTE: self._case.account_type.value,
        }

    def _round_attributes(self) -> dict[str, str | int]:
        return {
            **self._case_attributes(),
            RESUBMISSION_ROUND_ATTRIBUTE: self._case.resubmission_round,
        }

    def _outcome_attributes(self) -> dict[str, str | int]:
        attributes: dict[str, str | int] = {
            RESUBMISSION_ROUND_ATTRIBUTE: self._case.resubmission_round,
            OUTCOME_ATTRIBUTE: str(self._case.outcome),
        }
        if self._case.escalation_reason is not None:
            attributes[ESCALATION_REASON_ATTRIBUTE] = self._case.escalation_reason.value
        return attributes


def _sorted_values(document_types: Iterable[DocumentType]) -> list[str]:
    return sorted({t.value for t in document_types})


def _tracer() -> trace.Tracer:
    return trace.get_tracer(__name__)


def _case_not_in_review(status: CaseStatus) -> ApplicationError:
    return ApplicationError(
        f"case is {status}, not awaiting a review",
        type=CASE_NOT_IN_REVIEW_ERROR,
        non_retryable=True,
    )
