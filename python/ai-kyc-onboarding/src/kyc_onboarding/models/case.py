from datetime import timedelta

from pydantic import BaseModel, Field

from kyc_onboarding.models.decisions import AssessmentDecision, ReviewDecision
from kyc_onboarding.models.documents import SubmittedDocument
from kyc_onboarding.models.enums import (
    AccountType,
    CaseFault,
    CaseOutcome,
    CaseStatus,
    DocumentType,
    EscalationReason,
)


_REQUIRED_DOCUMENTS: dict[AccountType, tuple[DocumentType, ...]] = {
    AccountType.personal: (DocumentType.id, DocumentType.proof_of_address),
    AccountType.business: (
        DocumentType.id,
        DocumentType.proof_of_address,
        DocumentType.registration_certificate,
    ),
}


def required_documents_for(account_type: AccountType) -> tuple[DocumentType, ...]:
    return _REQUIRED_DOCUMENTS[account_type]


class Case(BaseModel):
    case_id: str
    name: str
    country: str
    account_type: AccountType
    status: CaseStatus = CaseStatus.awaiting_documents
    submitted_documents: list[SubmittedDocument] = Field(default_factory=list)
    resubmission_round: int = 0
    decisions: list[AssessmentDecision] = Field(default_factory=list)
    review: ReviewDecision | None = None
    outcome: CaseOutcome | None = None
    escalation_reason: EscalationReason | None = None

    @property
    def required_documents(self) -> tuple[DocumentType, ...]:
        return required_documents_for(self.account_type)

    @property
    def missing_documents(self) -> list[DocumentType]:
        submitted = {document.document_type for document in self.submitted_documents}
        return [
            document_type
            for document_type in self.required_documents
            if document_type not in submitted
        ]


class CaseInput(BaseModel):
    """Workflow input for one case. The API fills the deadlines, budget, prompt versions and
    fault from its settings, so workflow code never reads the environment."""

    case_id: str
    name: str
    country: str
    account_type: AccountType
    document_deadline: timedelta
    review_deadline: timedelta
    request_budget: int = Field(gt=0)
    extraction_prompt_version: str
    assessment_prompt_version: str
    fault: CaseFault | None = None


class CaseStatusView(BaseModel):
    case_id: str
    account_type: AccountType
    status: CaseStatus
    missing_documents: list[DocumentType]
    resubmission_round: int
    decisions: list[AssessmentDecision]
    review: ReviewDecision | None
    outcome: CaseOutcome | None
    escalation_reason: EscalationReason | None

    @classmethod
    def of(cls, case: Case) -> CaseStatusView:
        return cls(
            case_id=case.case_id,
            account_type=case.account_type,
            status=case.status,
            missing_documents=case.missing_documents,
            resubmission_round=case.resubmission_round,
            decisions=list(case.decisions),
            review=case.review,
            outcome=case.outcome,
            escalation_reason=case.escalation_reason,
        )
