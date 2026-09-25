from datetime import date

from kyc_onboarding.models.documents import (
    ExtractedIdFields,
    ExtractedProofOfAddressFields,
    ExtractedRegistrationCertificateFields,
)
from kyc_onboarding.tools.identity import compare_identity


def id_fields(**overrides: object) -> ExtractedIdFields:
    defaults: dict[str, object] = {
        "full_name": "Maria Elena Gonzalez",
        "date_of_birth": date(1988, 4, 12),
        "id_number": "NIC-778241",
        "declared_address": "24 Windmill Lane, Dublin, D02 X285",
    }
    defaults.update(overrides)
    return ExtractedIdFields(**defaults)  # type: ignore[arg-type]


def proof_of_address_fields(**overrides: object) -> ExtractedProofOfAddressFields:
    defaults: dict[str, object] = {
        "account_holder": "Maria Elena Gonzalez",
        "address": "24 Windmill Lane, Dublin, D02 X285",
    }
    defaults.update(overrides)
    return ExtractedProofOfAddressFields(**defaults)  # type: ignore[arg-type]


def registration_certificate_fields(**overrides: object) -> ExtractedRegistrationCertificateFields:
    defaults: dict[str, object] = {
        "company_name": "Meridian Trading Co Ltd",
        "registration_number": "REG-2019-004471",
        "address": "12 Fenwick Business Park, Cape Town, 8001",
        "authorized_representative": "Daniel Otieno Mwangi",
        "authorized_representative_date_of_birth": date(1979, 11, 3),
    }
    defaults.update(overrides)
    return ExtractedRegistrationCertificateFields(**defaults)  # type: ignore[arg-type]


class TestPersonalIdentity:
    def test_matching_documents_have_no_mismatches(self) -> None:
        result = compare_identity(
            id_fields=id_fields(),
            proof_of_address_fields=proof_of_address_fields(),
        )
        assert result.match is True
        assert result.mismatches == []

    def test_name_tolerant_of_case_spacing_and_order(self) -> None:
        result = compare_identity(
            id_fields=id_fields(full_name="Maria Elena Gonzalez"),
            proof_of_address_fields=proof_of_address_fields(
                account_holder="gonzalez   maria  elena"
            ),
        )
        assert result.match is True

    def test_genuinely_different_name_is_flagged(self) -> None:
        result = compare_identity(
            id_fields=id_fields(full_name="Maria Elena Gonzalez"),
            proof_of_address_fields=proof_of_address_fields(account_holder="Carla Fernandez"),
        )
        assert result.match is False
        assert any("name" in reason for reason in result.mismatches)

    def test_address_mismatch_is_flagged(self) -> None:
        result = compare_identity(
            id_fields=id_fields(declared_address="24 Windmill Lane, Dublin, D02 X285"),
            proof_of_address_fields=proof_of_address_fields(
                address="88 Larkspur Avenue, Toronto, M4E 3C5"
            ),
        )
        assert result.match is False
        assert any("address" in reason for reason in result.mismatches)

    def test_address_tolerant_of_case_and_spacing(self) -> None:
        result = compare_identity(
            id_fields=id_fields(declared_address="24 Windmill Lane, Dublin, D02 X285"),
            proof_of_address_fields=proof_of_address_fields(
                address="24   windmill lane,  dublin, d02 x285"
            ),
        )
        assert result.match is True

    def test_no_declared_address_on_id_skips_address_check(self) -> None:
        result = compare_identity(
            id_fields=id_fields(declared_address=None),
            proof_of_address_fields=proof_of_address_fields(address="anything at all"),
        )
        assert result.match is True

    def test_id_only_has_nothing_to_compare(self) -> None:
        result = compare_identity(id_fields=id_fields())
        assert result.match is True


class TestBusinessIdentity:
    def test_matching_business_documents_have_no_mismatches(self) -> None:
        result = compare_identity(
            id_fields=id_fields(full_name="Daniel Otieno Mwangi", date_of_birth=date(1979, 11, 3)),
            proof_of_address_fields=proof_of_address_fields(
                account_holder="Meridian Trading Co Ltd",
                address="12 Fenwick Business Park, Cape Town, 8001",
            ),
            registration_certificate_fields=registration_certificate_fields(),
        )
        assert result.match is True

    def test_representative_name_mismatch_is_flagged(self) -> None:
        result = compare_identity(
            id_fields=id_fields(full_name="Someone Else Entirely", date_of_birth=date(1979, 11, 3)),
            registration_certificate_fields=registration_certificate_fields(),
        )
        assert result.match is False
        assert any("name" in reason for reason in result.mismatches)

    def test_representative_date_of_birth_mismatch_is_flagged(self) -> None:
        result = compare_identity(
            id_fields=id_fields(full_name="Daniel Otieno Mwangi", date_of_birth=date(1980, 1, 1)),
            registration_certificate_fields=registration_certificate_fields(),
        )
        assert result.match is False
        assert any("date of birth" in reason for reason in result.mismatches)

    def test_business_address_mismatch_is_flagged(self) -> None:
        result = compare_identity(
            proof_of_address_fields=proof_of_address_fields(
                account_holder="Meridian Trading Co Ltd",
                address="a completely different street",
            ),
            registration_certificate_fields=registration_certificate_fields(),
        )
        assert result.match is False
        assert any("address" in reason for reason in result.mismatches)

    def test_proof_of_address_company_name_is_not_compared_to_representative(self) -> None:
        result = compare_identity(
            id_fields=id_fields(full_name="Daniel Otieno Mwangi", date_of_birth=date(1979, 11, 3)),
            proof_of_address_fields=proof_of_address_fields(
                account_holder="Meridian Trading Co Ltd",
                address="12 Fenwick Business Park, Cape Town, 8001",
            ),
            registration_certificate_fields=registration_certificate_fields(),
        )
        assert result.match is True
