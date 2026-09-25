import threading
from collections.abc import Sequence
from dataclasses import replace

import pytest
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    TextPart,
    ToolCallPart,
    UserPromptPart,
)
from pydantic_ai.models import ModelRequestParameters
from pydantic_ai.models.function import AgentInfo, FunctionModel
from temporalio.testing import ActivityEnvironment

from kyc_onboarding.agents.faults import (
    MODEL_UNAVAILABLE_HEARTBEAT,
    FaultInjectingModel,
    StaticFaultRegistry,
)
from kyc_onboarding.models.enums import CaseFault


CASE_ID = "case-1"
PARAMS = ModelRequestParameters()


def _respond(messages: list[ModelRequest], info: AgentInfo) -> ModelResponse:
    return ModelResponse(parts=[ToolCallPart(tool_name="final_result", args={"full_name": "Jane"})])


def _make_model(fault: CaseFault | None, *, injects_bad_output: bool = True) -> FaultInjectingModel:
    registry = StaticFaultRegistry({CASE_ID: fault} if fault else None)
    return FaultInjectingModel(
        FunctionModel(_respond), faults=registry, injects_bad_output=injects_bad_output
    )


def _activity_env(*, attempt: int, heartbeat_details: Sequence[object] = ()) -> ActivityEnvironment:
    env = ActivityEnvironment()
    env.info = replace(
        env.info, workflow_id=CASE_ID, attempt=attempt, heartbeat_details=heartbeat_details
    )
    return env


class _ThreadRecordingRegistry(StaticFaultRegistry):
    """Records which thread called each method."""

    def __init__(self, faults: dict[str, CaseFault] | None = None) -> None:
        super().__init__(faults)
        self.fault_for_thread: int | None = None
        self.consume_once_thread: int | None = None

    def fault_for(self, case_id: str) -> CaseFault | None:
        self.fault_for_thread = threading.get_ident()
        return super().fault_for(case_id)

    def consume_once(self, case_id: str, fault: CaseFault) -> bool:
        self.consume_once_thread = threading.get_ident()
        return super().consume_once(case_id, fault)


class TestOutsideAnActivity:
    async def test_is_transparent_regardless_of_the_configured_fault(self) -> None:
        model = _make_model(CaseFault.model_unavailable)

        response = await model.request([], None, PARAMS)

        assert isinstance(response.parts[0], ToolCallPart)
        assert response.parts[0].args == {"full_name": "Jane"}


class TestModelUnavailable:
    async def test_the_first_model_activity_fails_its_first_two_attempts(self) -> None:
        model = _make_model(CaseFault.model_unavailable)
        heartbeats: list[object] = []

        first = _activity_env(attempt=1)
        first.on_heartbeat = lambda *details: heartbeats.extend(details)
        with pytest.raises(ConnectionError):
            await first.run(model.request, [], None, PARAMS)
        with pytest.raises(ConnectionError):
            await _activity_env(attempt=2, heartbeat_details=heartbeats).run(
                model.request, [], None, PARAMS
            )
        response = await _activity_env(attempt=3, heartbeat_details=heartbeats).run(
            model.request, [], None, PARAMS
        )

        assert heartbeats == [MODEL_UNAVAILABLE_HEARTBEAT]
        assert isinstance(response.parts[0], ToolCallPart)

    async def test_later_model_activities_of_the_case_run_clean(self) -> None:
        model = _make_model(CaseFault.model_unavailable)
        with pytest.raises(ConnectionError):
            await _activity_env(attempt=1).run(model.request, [], None, PARAMS)

        response = await _activity_env(attempt=1).run(model.request, [], None, PARAMS)

        assert isinstance(response.parts[0], ToolCallPart)

    async def test_a_retry_without_the_marker_runs_clean(self) -> None:
        model = _make_model(CaseFault.model_unavailable)
        with pytest.raises(ConnectionError):
            await _activity_env(attempt=1).run(model.request, [], None, PARAMS)

        response = await _activity_env(attempt=2).run(model.request, [], None, PARAMS)

        assert isinstance(response.parts[0], ToolCallPart)

    async def test_does_not_share_its_claim_with_bad_output(self) -> None:
        registry = StaticFaultRegistry({CASE_ID: CaseFault.model_unavailable})
        registry.consume_once(CASE_ID, CaseFault.bad_output)
        model = FaultInjectingModel(FunctionModel(_respond), faults=registry)

        with pytest.raises(ConnectionError):
            await _activity_env(attempt=1).run(model.request, [], None, PARAMS)

    async def test_a_different_fault_never_raises(self) -> None:
        model = _make_model(CaseFault.sanctions_down)
        env = _activity_env(attempt=1)

        response = await env.run(model.request, [], None, PARAMS)

        assert isinstance(response.parts[0], ToolCallPart)


class TestBadOutput:
    async def test_corrupts_a_fresh_response(self) -> None:
        model = _make_model(CaseFault.bad_output)
        env = _activity_env(attempt=1)
        messages = [ModelRequest(parts=[UserPromptPart(content="extract")])]

        response = await env.run(model.request, messages, None, PARAMS)

        assert response.parts == [TextPart(content='{"full_name":"Jane"}')]

    async def test_does_not_corrupt_a_corrective_resubmission(self) -> None:
        model = _make_model(CaseFault.bad_output)
        env = _activity_env(attempt=1)
        messages = [
            ModelRequest(parts=[UserPromptPart(content="extract")]),
            ModelResponse(parts=[ToolCallPart(tool_name="final_result", args={})]),
            ModelRequest(parts=[RetryPromptPart(content="invalid output")]),
        ]

        response = await env.run(model.request, messages, None, PARAMS)

        part = response.parts[0]
        assert isinstance(part, ToolCallPart)
        assert part.args == {"full_name": "Jane"}

    async def test_no_fault_never_corrupts(self) -> None:
        model = _make_model(None)
        env = _activity_env(attempt=1)

        response = await env.run(model.request, [], None, PARAMS)

        part = response.parts[0]
        assert isinstance(part, ToolCallPart)
        assert part.args == {"full_name": "Jane"}

    async def test_fires_once_per_case_not_once_per_fresh_request(self) -> None:
        model = _make_model(CaseFault.bad_output)
        first_document = [ModelRequest(parts=[UserPromptPart(content="extract document 1")])]
        second_document = [ModelRequest(parts=[UserPromptPart(content="extract document 2")])]

        first = await _activity_env(attempt=1).run(model.request, first_document, None, PARAMS)
        second = await _activity_env(attempt=1).run(model.request, second_document, None, PARAMS)

        assert first.parts == [TextPart(content='{"full_name":"Jane"}')]

        second_part = second.parts[0]
        assert isinstance(second_part, ToolCallPart)
        assert second_part.args == {"full_name": "Jane"}

    async def test_assessment_model_never_corrupts(self) -> None:
        model = _make_model(CaseFault.bad_output, injects_bad_output=False)
        env = _activity_env(attempt=1)
        messages = [ModelRequest(parts=[UserPromptPart(content="assess")])]

        response = await env.run(model.request, messages, None, PARAMS)

        part = response.parts[0]
        assert isinstance(part, ToolCallPart)
        assert part.args == {"full_name": "Jane"}


class TestRegistryCallsRunOffTheEventLoopThread:
    async def test_fault_for_and_consume_once_run_in_a_worker_thread(self) -> None:
        registry = _ThreadRecordingRegistry({CASE_ID: CaseFault.bad_output})
        model = FaultInjectingModel(FunctionModel(_respond), faults=registry)
        env = _activity_env(attempt=1)
        messages = [ModelRequest(parts=[UserPromptPart(content="extract")])]
        main_thread = threading.get_ident()

        await env.run(model.request, messages, None, PARAMS)

        assert registry.fault_for_thread is not None
        assert registry.fault_for_thread != main_thread
        assert registry.consume_once_thread is not None
        assert registry.consume_once_thread != main_thread
