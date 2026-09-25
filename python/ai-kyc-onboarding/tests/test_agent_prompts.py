import pytest

from kyc_onboarding.agents.prompts import PROMPT_VERSION_METADATA_KEY, load_prompt


class TestLoadPrompt:
    def test_loads_extraction_v1_by_name(self) -> None:
        prompt = load_prompt("extraction_v1")

        assert "extract" in prompt.system.lower()
        assert "{document_type}" in prompt.user
        assert "{document_text}" in prompt.user

    def test_loads_assessment_v2_by_name(self) -> None:
        prompt = load_prompt("assessment_v2")

        assert "check_expiry" in prompt.system
        assert "compare_identity" in prompt.system
        assert "screen_sanctions" in prompt.system
        assert "{case_id}" in prompt.user
        assert "{account_type}" in prompt.user
        assert "{extracted_documents}" in prompt.user

    def test_assessment_v2_asks_for_the_tools_first_then_a_json_decision(self) -> None:
        prompt = load_prompt("assessment_v2")

        assert "final_result" not in prompt.system
        assert "Call the tools first" in prompt.system
        assert "```json code block" in prompt.system

    def test_assessment_v2_escalates_a_partial_sanctions_result(self) -> None:
        prompt = load_prompt("assessment_v2")

        assert "partial" in prompt.system
        assert "even when the spelling differs" in prompt.system

    def test_assessment_v3_keeps_v2_and_asks_for_the_id_when_its_expiry_is_missing(self) -> None:
        v2 = load_prompt("assessment_v2")
        v3 = load_prompt("assessment_v3")

        assert v3.user == v2.user
        for paragraph in v2.system.strip().split("\n\n"):
            assert paragraph in v3.system
        assert "expiry date missing" in v3.system
        assert "Request resubmission of the ID" in v3.system

    def test_double_braced_placeholders_become_single_braced(self) -> None:
        prompt = load_prompt("extraction_v1")

        assert "{{" not in prompt.user
        assert "}}" not in prompt.user

    def test_user_prompt_formats_with_the_expected_keys(self) -> None:
        prompt = load_prompt("extraction_v1")

        rendered = prompt.user.format(document_type="id", document_text="Jane Doe, ID 123")

        assert "Document type: id" in rendered
        assert "Jane Doe, ID 123" in rendered

    def test_unknown_prompt_name_raises(self) -> None:
        with pytest.raises(FileNotFoundError):
            load_prompt("no_such_prompt")

    def test_prompt_version_metadata_key_is_stable(self) -> None:
        assert PROMPT_VERSION_METADATA_KEY == "prompt_version"
