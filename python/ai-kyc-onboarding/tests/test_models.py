from datetime import date

import pytest
from pydantic import ValidationError

from kyc_onboarding.models import (
    AccountType,
    ApproveDecision,
    Case,
    CaseStatus,
    DocumentType,
    EscalateDecision,
    ExtractedDocument,
    ExtractedIdFields,
    ExtractedProofOfAddressFields,
    ExtractedRegistrationCertificateFields,
    RequestResubmissionDecision,
    RiskLevel,
    SubmittedDocument,
    required_documents_for,
)


class TestRequiredDocuments:
    def test_personal_needs_id_and_proof_of_address(self) -> None:
        assert required_documents_for(AccountType.personal) == (
            DocumentType.id,
            DocumentType.proof_of_address,
        )

    def test_business_also_needs_registration_certificate(self) -> None:
        assert required_documents_for(AccountType.business) == (
            DocumentType.id,
            DocumentType.proof_of_address,
            DocumentType.registration_certificate,
        )


class TestCase:
    def test_missing_documents_starts_as_all_required(self) -> None:
        case = Case(
            case_id="case-1", name="Maria Gonzalez", country="IE", account_type=AccountType.personal
        )
        assert case.status == CaseStatus.awaiting_documents
        assert case.missing_documents == [DocumentType.id, DocumentType.proof_of_address]

    def test_missing_documents_shrinks_as_documents_arrive(self) -> None:
        case = Case(
            case_id="case-1",
            name="Maria Gonzalez",
            country="IE",
            account_type=AccountType.personal,
            submitted_documents=[SubmittedDocument(document_type=DocumentType.id, raw_text="...")],
        )
        assert case.missing_documents == [DocumentType.proof_of_address]

    def test_decisions_accept_each_discriminated_variant(self) -> None:
        case = Case(
            case_id="case-1",
            name="Maria Gonzalez",
            country="IE",
            account_type=AccountType.personal,
            decisions=[
                RequestResubmissionDecision(
                    reasons=["address mismatch"],
                    documents_to_resend=[DocumentType.proof_of_address],
                ),
                EscalateDecision(risk_level=RiskLevel.high, reasons=["partial sanctions match"]),
                ApproveDecision(),
            ],
        )
        assert [decision.decision for decision in case.decisions] == [
            "request_resubmission",
            "escalate",
            "approve",
        ]

    def test_decision_round_trips_through_json(self) -> None:
        case = Case(
            case_id="case-1",
            name="Maria Gonzalez",
            country="IE",
            account_type=AccountType.personal,
            decisions=[EscalateDecision(risk_level=RiskLevel.medium, reasons=["partial match"])],
        )
        restored = Case.model_validate_json(case.model_dump_json())
        assert restored.decisions[0].decision == "escalate"


class TestExtractedFields:
    def test_id_fields_require_date_of_birth(self) -> None:
        with pytest.raises(ValidationError):
            ExtractedIdFields(full_name="Maria Gonzalez", id_number="NIC-1")  # type: ignore[call-arg]

    def test_id_fields_allow_optional_declared_address(self) -> None:
        fields = ExtractedIdFields(
            full_name="Maria Gonzalez",
            date_of_birth=date(1988, 4, 12),
            id_number="NIC-778241",
        )
        assert fields.declared_address is None
        assert fields.expiry_date is None

    def test_extracted_document_wraps_registration_certificate_fields(self) -> None:
        document = ExtractedDocument(
            document_type=DocumentType.registration_certificate,
            fields=ExtractedRegistrationCertificateFields(
                company_name="Meridian Trading Co Ltd",
                registration_number="REG-2019-004471",
                address="12 Fenwick Business Park, Cape Town, 8001",
                authorized_representative="Daniel Otieno Mwangi",
            ),
        )
        assert isinstance(document.fields, ExtractedRegistrationCertificateFields)

    def test_extracted_document_wraps_proof_of_address_fields(self) -> None:
        document = ExtractedDocument(
            document_type=DocumentType.proof_of_address,
            fields=ExtractedProofOfAddressFields(
                account_holder="Maria Gonzalez",
                address="24 Windmill Lane, Dublin, D02 X285",
            ),
        )
        assert isinstance(document.fields, ExtractedProofOfAddressFields)


class TestDecisions:
    def test_request_resubmission_requires_reasons_and_documents(self) -> None:
        decision = RequestResubmissionDecision(
            reasons=["expired ID"],
            documents_to_resend=[DocumentType.id],
        )
        assert decision.decision == "request_resubmission"
        assert decision.documents_to_resend == [DocumentType.id]

    def test_escalate_requires_risk_level(self) -> None:
        with pytest.raises(ValidationError):
            EscalateDecision(reasons=["partial match"])  # type: ignore[call-arg]

    def test_request_resubmission_needs_at_least_one_reason(self) -> None:
        with pytest.raises(ValidationError, match="at least 1 item"):
            RequestResubmissionDecision(reasons=[], documents_to_resend=[DocumentType.id])

    def test_escalate_needs_at_least_one_reason(self) -> None:
        with pytest.raises(ValidationError, match="at least 1 item"):
            EscalateDecision(risk_level=RiskLevel.medium, reasons=[])
