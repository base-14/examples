from typing import Annotated, Literal

from pydantic import BaseModel, Field

from kyc_onboarding.models.enums import DocumentType, RiskLevel


class ApproveDecision(BaseModel):
    decision: Literal["approve"] = "approve"


class RequestResubmissionDecision(BaseModel):
    decision: Literal["request_resubmission"] = "request_resubmission"
    reasons: list[str] = Field(min_length=1)
    documents_to_resend: list[DocumentType]


class EscalateDecision(BaseModel):
    decision: Literal["escalate"] = "escalate"
    risk_level: RiskLevel
    reasons: list[str] = Field(min_length=1)


AssessmentDecision = Annotated[
    ApproveDecision | RequestResubmissionDecision | EscalateDecision,
    Field(discriminator="decision"),
]


class AssessmentAnswer(BaseModel):
    """The assessment agent's answer: every decision's fields in one flat object, keyed by
    `decision`. `agents.assessment.decision_from_answer` turns it into an `AssessmentDecision`.
    """

    decision: Literal["approve", "request_resubmission", "escalate"]
    reasons: list[str] = []
    documents_to_resend: list[DocumentType] = []
    risk_level: RiskLevel | None = None


class ReviewDecision(BaseModel):
    decision: Literal["approve", "reject"]
    reviewer: str
    note: str | None = None
