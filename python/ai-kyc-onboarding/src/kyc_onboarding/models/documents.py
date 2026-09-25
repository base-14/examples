from datetime import date

from pydantic import BaseModel, Field

from kyc_onboarding.models.enums import DocumentType


class SubmittedDocument(BaseModel):
    document_type: DocumentType
    raw_text: str


class ExtractedIdFields(BaseModel):
    full_name: str
    date_of_birth: date
    id_number: str
    declared_address: str | None = None
    expiry_date: date | None = None


class ExtractedProofOfAddressFields(BaseModel):
    account_holder: str
    address: str
    issued_date: date | None = None


class ExtractedRegistrationCertificateFields(BaseModel):
    company_name: str
    registration_number: str
    address: str
    authorized_representative: str
    authorized_representative_date_of_birth: date | None = None
    incorporation_date: date | None = None


ExtractedFields = (
    ExtractedIdFields | ExtractedProofOfAddressFields | ExtractedRegistrationCertificateFields
)


class ExtractedDocument(BaseModel):
    document_type: DocumentType
    fields: ExtractedFields = Field(union_mode="left_to_right")
