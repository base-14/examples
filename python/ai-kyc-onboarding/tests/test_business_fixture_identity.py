from datetime import date

from kyc_onboarding.fixtures import load_fixture_set
from kyc_onboarding.models.documents import (
    ExtractedIdFields,
    ExtractedProofOfAddressFields,
    ExtractedRegistrationCertificateFields,
    SubmittedDocument,
)
from kyc_onboarding.models.enums import DocumentType
from kyc_onboarding.tools.identity import compare_identity


def _parse_fields(raw_text: str) -> dict[str, str]:
    fields = {}
    for line in raw_text.splitlines()[1:]:
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        fields[key.strip()] = value.strip()
    return fields


def _document(documents: list[SubmittedDocument], document_type: DocumentType) -> SubmittedDocument:
    return next(document for document in documents if document.document_type == document_type)


def _id_fields(documents: list[SubmittedDocument]) -> ExtractedIdFields:
    parsed = _parse_fields(_document(documents, DocumentType.id).raw_text)
    return ExtractedIdFields(
        full_name=parsed["Full name"],
        date_of_birth=date.fromisoformat(parsed["Date of birth"]),
        id_number=parsed["ID number"],
        declared_address=parsed.get("Address"),
    )


def _proof_of_address_fields(documents: list[SubmittedDocument]) -> ExtractedProofOfAddressFields:
    parsed = _parse_fields(_document(documents, DocumentType.proof_of_address).raw_text)
    return ExtractedProofOfAddressFields(
        account_holder=parsed["Account holder"],
        address=parsed["Service address"],
    )


def _registration_certificate_fields(
    documents: list[SubmittedDocument],
) -> ExtractedRegistrationCertificateFields:
    parsed = _parse_fields(_document(documents, DocumentType.registration_certificate).raw_text)
    return ExtractedRegistrationCertificateFields(
        company_name=parsed["Company name"],
        registration_number=parsed["Registration number"],
        address=parsed["Registered address"],
        authorized_representative=parsed["Authorized representative"],
        authorized_representative_date_of_birth=date.fromisoformat(
            parsed["Representative date of birth"]
        ),
    )


class TestBusinessFixtureIdentity:
    def test_address_mismatch_business_reports_address_mismatch(self) -> None:
        documents = load_fixture_set("address_mismatch_business")
        result = compare_identity(
            id_fields=_id_fields(documents),
            proof_of_address_fields=_proof_of_address_fields(documents),
            registration_certificate_fields=_registration_certificate_fields(documents),
        )
        assert result.match is False
        assert any(
            "address" in reason and "registration_certificate" in reason
            for reason in result.mismatches
        )

    def test_corrected_address_business_matches(self) -> None:
        documents = load_fixture_set("corrected_address_business")
        result = compare_identity(
            id_fields=_id_fields(documents),
            proof_of_address_fields=_proof_of_address_fields(documents),
            registration_certificate_fields=_registration_certificate_fields(documents),
        )
        assert result.match is True
        assert result.mismatches == []
