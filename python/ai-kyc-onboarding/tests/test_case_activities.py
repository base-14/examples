from google.protobuf.timestamp_pb2 import Timestamp
from temporalio.api.common.v1 import Payload

from scripts.case_activities import _decode, _describe_activity, _has_retry_prompt, _unix_time


MODEL_REQUEST = "agent__kyc-extraction__model_request"
CALL_TOOL = "agent__kyc-assessment__toolset__<agent>__call_tool"


class TestDecode:
    def test_decodes_json_payloads(self) -> None:
        payloads = [Payload(data=b'{"name": "screen_sanctions"}'), Payload(data=b"3")]

        assert _decode(payloads) == [{"name": "screen_sanctions"}, 3]

    def test_keeps_a_slot_for_a_payload_that_is_not_json(self) -> None:
        payloads = [Payload(data=b"\x00binary"), Payload(data=b"true")]

        assert _decode(payloads) == [None, True]


class TestHasRetryPrompt:
    def test_true_when_a_message_carries_a_retry_prompt_part(self) -> None:
        request = {
            "messages": [
                {"parts": [{"part_kind": "user-prompt"}]},
                {"parts": [{"part_kind": "text"}]},
                {"parts": [{"part_kind": "retry-prompt"}]},
            ]
        }

        assert _has_retry_prompt(request) is True

    def test_false_for_a_fresh_request(self) -> None:
        request = {"messages": [{"parts": [{"part_kind": "user-prompt"}]}]}

        assert _has_retry_prompt(request) is False

    def test_false_for_an_input_that_is_not_a_request(self) -> None:
        assert _has_retry_prompt(None) is False
        assert _has_retry_prompt(["not", "a", "request"]) is False


class TestDescribeActivity:
    def test_model_request_names_its_agent_and_retry_prompt(self) -> None:
        request = {"messages": [{"parts": [{"part_kind": "retry-prompt"}]}]}

        assert _describe_activity(MODEL_REQUEST, request) == {
            "agent": "kyc-extraction",
            "kind": "model_request",
            "tool": None,
            "has_retry_prompt": True,
        }

    def test_tool_call_names_its_tool(self) -> None:
        assert _describe_activity(CALL_TOOL, {"name": "screen_sanctions"}) == {
            "agent": "kyc-assessment",
            "kind": "call_tool",
            "tool": "screen_sanctions",
            "has_retry_prompt": False,
        }

    def test_tool_call_with_an_undecodable_input_has_no_tool(self) -> None:
        assert _describe_activity(CALL_TOOL, None)["tool"] is None

    def test_other_activity_types_keep_their_type_as_the_kind(self) -> None:
        assert _describe_activity("send_email", None) == {
            "agent": None,
            "kind": "send_email",
            "tool": None,
            "has_retry_prompt": False,
        }


class TestUnixTime:
    def test_converts_an_event_time_to_fractional_seconds(self) -> None:
        assert _unix_time(Timestamp(seconds=1_790_000_000, nanos=250_000_000)) == 1_790_000_000.25
