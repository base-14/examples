from enum import StrEnum


class AccountType(StrEnum):
    personal = "personal"
    business = "business"


class DocumentType(StrEnum):
    id = "id"
    proof_of_address = "proof_of_address"
    registration_certificate = "registration_certificate"


class CaseStatus(StrEnum):
    awaiting_documents = "awaiting_documents"
    assessing = "assessing"
    awaiting_review = "awaiting_review"
    approved = "approved"
    rejected = "rejected"
    expired = "expired"


class CaseOutcome(StrEnum):
    approved = "approved"
    rejected = "rejected"
    expired = "expired"


class RiskLevel(StrEnum):
    low = "low"
    medium = "medium"
    high = "high"


class EscalationReason(StrEnum):
    risk = "risk"
    agent_error = "agent_error"
    budget = "budget"
    invalid_output = "invalid_output"


class CaseFault(StrEnum):
    model_unavailable = "model_unavailable"
    sanctions_down = "sanctions_down"
    bad_output = "bad_output"
    tight_budget = "tight_budget"
