import re
from datetime import date

import pytest

from kyc_onboarding.fixtures import list_fixture_sets, load_fixture_set
from kyc_onboarding.models.enums import DocumentType


SCENARIOS_WITH_ALL_REQUIRED_PERSONAL_DOCS = {
    "clean_personal",
    "address_mismatch",
    "partial_sanctions_match",
    "expired_id",
}

SCENARIOS_WITH_ALL_REQUIRED_BUSINESS_DOCS = {
    "clean_business",
    "address_mismatch_business",
    "corrected_address_business",
}


class TestListFixtureSets:
    def test_lists_every_scenario(self) -> None:
        assert list_fixture_sets() == [
            "address_mismatch",
            "address_mismatch_business",
            "clean_business",
            "clean_personal",
            "corrected_address",
            "corrected_address_business",
            "expired_id",
            "partial_sanctions_match",
        ]


class TestLoadFixtureSet:
    @pytest.mark.parametrize("scenario", sorted(SCENARIOS_WITH_ALL_REQUIRED_PERSONAL_DOCS))
    def test_personal_scenarios_carry_id_and_proof_of_address(self, scenario: str) -> None:
        documents = load_fixture_set(scenario)
        document_types = {document.document_type for document in documents}
        assert document_types == {DocumentType.id, DocumentType.proof_of_address}

    @pytest.mark.parametrize("scenario", sorted(SCENARIOS_WITH_ALL_REQUIRED_BUSINESS_DOCS))
    def test_business_scenarios_carry_all_three_documents(self, scenario: str) -> None:
        documents = load_fixture_set(scenario)
        document_types = {document.document_type for document in documents}
        assert document_types == {
            DocumentType.id,
            DocumentType.proof_of_address,
            DocumentType.registration_certificate,
        }

    def test_corrected_address_carries_only_the_resent_document(self) -> None:
        documents = load_fixture_set("corrected_address")
        assert [document.document_type for document in documents] == [DocumentType.proof_of_address]

    def test_documents_carry_non_empty_raw_text(self) -> None:
        for document in load_fixture_set("clean_personal"):
            assert document.raw_text.strip() != ""

    def test_unknown_scenario_raises(self) -> None:
        with pytest.raises(FileNotFoundError):
            load_fixture_set("does_not_exist")


MONTH_NAME = re.compile(
    r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\b"
)


def _labelled_lines(raw_text: str) -> dict[str, str]:
    fields = {}
    for line in raw_text.splitlines()[1:]:
        label, _, value = line.partition(":")
        fields[label.strip()] = value.strip()
    return fields


class TestFixtureDates:
    @pytest.mark.parametrize("scenario", list_fixture_sets())
    def test_no_date_is_written_with_a_month_name(self, scenario: str) -> None:
        for document in load_fixture_set(scenario):
            assert MONTH_NAME.search(document.raw_text) is None, document.raw_text

    @pytest.mark.parametrize("scenario", list_fixture_sets())
    def test_every_date_line_is_iso_formatted(self, scenario: str) -> None:
        for document in load_fixture_set(scenario):
            for label, value in _labelled_lines(document.raw_text).items():
                if "date" in label.lower():
                    date.fromisoformat(value)

    @pytest.mark.parametrize("scenario", list_fixture_sets())
    def test_proof_of_address_carries_an_iso_issue_date(self, scenario: str) -> None:
        for document in load_fixture_set(scenario):
            if document.document_type == DocumentType.proof_of_address:
                fields = _labelled_lines(document.raw_text)
                assert date.fromisoformat(fields["Date of issue"]) <= date(2026, 9, 24)


class TestBusinessFixtureAddresses:
    @pytest.mark.parametrize("scenario", sorted(SCENARIOS_WITH_ALL_REQUIRED_BUSINESS_DOCS))
    def test_the_representative_id_states_no_home_address_to_compare(self, scenario: str) -> None:
        id_document = next(
            document
            for document in load_fixture_set(scenario)
            if document.document_type == DocumentType.id
        )
        assert "Address" not in _labelled_lines(id_document.raw_text)
