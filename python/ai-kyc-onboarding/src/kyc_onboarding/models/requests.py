from pydantic import BaseModel, Field

from kyc_onboarding.models.enums import AccountType, CaseFault, DocumentType


class CaseCreateRequest(BaseModel):
    """`POST /cases` body. `fault` and the deadline and budget overrides are only honoured
    when `KYC_FAULTS_ENABLED=true`; the route refuses the request otherwise."""

    name: str
    country: str
    account_type: AccountType
    fault: CaseFault | None = None
    document_deadline_seconds: int | None = Field(default=None, gt=0)
    review_deadline_seconds: int | None = Field(default=None, gt=0)
    request_budget: int | None = Field(default=None, gt=0)

    @property
    def has_fault_overrides(self) -> bool:
        return (
            self.fault is not None
            or self.document_deadline_seconds is not None
            or self.review_deadline_seconds is not None
            or self.request_budget is not None
        )


class DocumentAccepted(BaseModel):
    case_id: str
    document_type: DocumentType
