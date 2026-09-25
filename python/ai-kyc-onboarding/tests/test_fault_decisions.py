from dataclasses import replace

from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    TextPart,
    ToolCallPart,
    UserPromptPart,
)

from kyc_onboarding.agents.faults import (
    MODEL_UNAVAILABLE_MAX_ATTEMPT,
    SANCTIONS_DOWN_MAX_ATTEMPT,
    StaticFaultRegistry,
    corrupt_response,
    has_retry_prompt,
    should_raise_model_unavailable,
    should_raise_sanctions_down,
)
from kyc_onboarding.models.enums import CaseFault


class TestShouldRaiseModelUnavailable:
    def test_no_fault_never_raises(self) -> None:
        assert should_raise_model_unavailable(None, 1) is False

    def test_other_fault_never_raises(self) -> None:
        assert should_raise_model_unavailable(CaseFault.sanctions_down, 1) is False

    def test_raises_up_to_the_max_attempt(self) -> None:
        for attempt in range(1, MODEL_UNAVAILABLE_MAX_ATTEMPT + 1):
            assert should_raise_model_unavailable(CaseFault.model_unavailable, attempt) is True

    def test_stops_raising_after_the_max_attempt(self) -> None:
        assert (
            should_raise_model_unavailable(
                CaseFault.model_unavailable, MODEL_UNAVAILABLE_MAX_ATTEMPT + 1
            )
            is False
        )


class TestShouldRaiseSanctionsDown:
    def test_no_fault_never_raises(self) -> None:
        assert should_raise_sanctions_down(None, 1) is False

    def test_raises_up_to_the_max_attempt(self) -> None:
        for attempt in range(1, SANCTIONS_DOWN_MAX_ATTEMPT + 1):
            assert should_raise_sanctions_down(CaseFault.sanctions_down, attempt) is True

    def test_stops_raising_after_the_max_attempt(self) -> None:
        assert (
            should_raise_sanctions_down(CaseFault.sanctions_down, SANCTIONS_DOWN_MAX_ATTEMPT + 1)
            is False
        )


class TestHasRetryPrompt:
    def test_false_for_a_fresh_request(self) -> None:
        messages = [ModelRequest(parts=[UserPromptPart(content="hello")])]

        assert has_retry_prompt(messages) is False

    def test_true_once_a_retry_prompt_part_is_present(self) -> None:
        messages = [
            ModelRequest(parts=[UserPromptPart(content="hello")]),
            ModelResponse(parts=[ToolCallPart(tool_name="final_result", args={})]),
            ModelRequest(parts=[RetryPromptPart(content="invalid output")]),
        ]

        assert has_retry_prompt(messages) is True


class TestCorruptResponse:
    def test_turns_an_output_tool_call_into_a_text_answer(self) -> None:
        response = ModelResponse(
            parts=[ToolCallPart(tool_name="final_result", args={"full_name": "Jane Doe"})]
        )

        corrupted = corrupt_response(response)

        assert corrupted.parts == [TextPart(content='{"full_name":"Jane Doe"}')]

    def test_keeps_a_text_only_response_as_text(self) -> None:
        response = ModelResponse(parts=[TextPart(content="a valid answer")])

        corrupted = corrupt_response(response)

        assert corrupted.parts == [TextPart(content="a valid answer")]

    def test_preserves_response_identity_fields(self) -> None:
        response = ModelResponse(
            parts=[ToolCallPart(tool_name="final_result", args={})],
            model_name="gemma4:e2b",
        )

        corrupted = corrupt_response(response)

        assert corrupted.model_name == response.model_name

    def test_replace_is_used_not_mutation(self) -> None:
        original = ModelResponse(parts=[ToolCallPart(tool_name="final_result", args={"a": 1})])
        untouched = replace(original)

        corrupt_response(original)

        assert original.parts[0] == untouched.parts[0]


class TestStaticFaultRegistry:
    def test_returns_none_for_an_unknown_case(self) -> None:
        registry = StaticFaultRegistry()

        assert registry.fault_for("case-1") is None

    def test_returns_the_configured_fault(self) -> None:
        registry = StaticFaultRegistry({"case-1": CaseFault.bad_output})

        assert registry.fault_for("case-1") == CaseFault.bad_output
        assert registry.fault_for("case-2") is None

    def test_consume_once_claims_the_first_call(self) -> None:
        registry = StaticFaultRegistry()

        assert registry.consume_once("case-1", CaseFault.bad_output) is True

    def test_consume_once_refuses_every_later_call(self) -> None:
        registry = StaticFaultRegistry()
        registry.consume_once("case-1", CaseFault.bad_output)

        assert registry.consume_once("case-1", CaseFault.bad_output) is False

    def test_consume_once_is_scoped_per_case_and_per_fault(self) -> None:
        registry = StaticFaultRegistry()
        registry.consume_once("case-1", CaseFault.bad_output)

        assert registry.consume_once("case-2", CaseFault.bad_output) is True
        assert registry.consume_once("case-1", CaseFault.model_unavailable) is True
