import asyncio
import json
import os
from collections.abc import AsyncIterator, Iterator
from typing import Any

import httpx
import pytest
from agents import FunctionTool, ModelResponse, Usage
from agents.models.interface import Model
from openai.types.responses import (
    ResponseFunctionToolCall,
    ResponseOutputMessage,
    ResponseOutputText,
)
from opentelemetry.instrumentation.genai.openai_agents import OpenAIAgentsInstrumentor

from filing_analyst.agents import BadOutput, QuestionTimedOut
from filing_analyst.budget import BudgetExceeded, CallBudget
from filing_analyst.frameworks.openai_agents import (
    OpenAIAgentsFramework,
    apply_capture_mode,
    openai_tools,
)
from filing_analyst.model_faults import INVENTED_ACCESSION
from filing_analyst.tools import ToolContext, bound_tools
from filing_analyst.verifier import ToolResultCollector, verify_answer
from tests.agent_support import (
    ANALYST_MODEL,
    FRAME_CALL,
    GOOD_ANSWER,
    LOOKUP,
    RANKING_MODEL,
    Call,
    Say,
    Stall,
    Turn,
    config,
    request,
)
from tests.sec_support import FakeClock, RecordingHandler, sec_client
from tests.span_capture import captured_spans, named
from tests.test_tools import FRAME
from tests.tools_support import WORKIVA, MemoryFacts


ANSWER = Call("FilingAnswer", GOOD_ANSWER)


class ScriptedModel(Model):
    """Plays back one turn per model call: a tool call or a closing message."""

    def __init__(self, turns: list[Any]) -> None:
        self.turns = list(turns)
        self.seen: list[Any] = []

    async def get_response(self, *args: Any, **kwargs: Any) -> ModelResponse:
        self.seen.append(kwargs["input"] if "input" in kwargs else args[1])
        turn: Turn = self.turns.pop(0) if self.turns else Say("Done.")
        if isinstance(turn, Stall):
            await asyncio.Event().wait()
        output: Any
        if isinstance(turn, Call):
            output = ResponseFunctionToolCall(
                type="function_call",
                call_id=f"c{len(self.seen)}",
                name=turn.name,
                arguments=json.dumps(turn.input),
            )
        else:
            output = ResponseOutputMessage(
                id=f"m{len(self.seen)}",
                type="message",
                role="assistant",
                status="completed",
                content=[ResponseOutputText(type="output_text", text=turn.text, annotations=[])],
            )
        return ModelResponse(
            output=[output],
            usage=Usage(requests=1, input_tokens=120, output_tokens=30, total_tokens=150),
            response_id=None,
        )

    def stream_response(self, *args: Any, **kwargs: Any) -> AsyncIterator[Any]:
        raise NotImplementedError


def tool_outputs(model: ScriptedModel) -> list[str]:
    """Every tool result the model was shown, from its last call."""
    return [
        str(item.get("output"))
        for item in model.seen[-1]
        if isinstance(item, dict) and item.get("type") == "function_call_output"
    ]


@pytest.fixture(scope="module", autouse=True)
def instrumented() -> Iterator[None]:
    """Replaces the SDK's own trace exporter, as the app does, so no test run reaches OpenAI."""
    instrumentor = OpenAIAgentsInstrumentor()
    instrumentor.instrument(disable_openai_trace_export=True)
    yield
    instrumentor.uninstrument()


@pytest.fixture(scope="module")
def facts() -> MemoryFacts:
    return MemoryFacts.of(WORKIVA)


class Run:
    def __init__(
        self, facts: MemoryFacts, analyst: list[Any], ranking: list[Any] | None = None
    ) -> None:
        self.analyst = ScriptedModel(analyst)
        self.ranking = ScriptedModel(ranking or [])
        self.collector = ToolResultCollector()
        self.frames = RecordingHandler(lambda _r: httpx.Response(200, json=FRAME))
        self.context = ToolContext(
            facts=facts, sec=sec_client(self.frames, FakeClock()), cik=WORKIVA
        )

    def model(self, model_id: str) -> ScriptedModel:
        assert model_id in (ANALYST_MODEL, RANKING_MODEL)
        return self.analyst if model_id == ANALYST_MODEL else self.ranking

    async def __call__(self, **changes: Any) -> Any:
        return await OpenAIAgentsFramework(self.model, think=False).run(
            request(**changes), config(), self.context, self.collector
        )


async def test_the_analyst_returns_the_typed_answer(facts: MemoryFacts) -> None:
    run = Run(facts, [LOOKUP, ANSWER])
    answer = await run()
    assert answer.figures[0].accession == "0001445305-22-000041"
    assert run.collector.results[0]["rows"][0]["value"] == -47479000
    assert verify_answer(answer, run.collector.results).passed


async def test_the_spans_carry_the_question_attributes(facts: MemoryFacts) -> None:
    memory = captured_spans()
    await Run(facts, [LOOKUP, ANSWER])(question_id="q-oai-1")
    spans = memory.get_finished_spans()
    (agent,) = named(spans, "invoke_agent analyst")
    attributes = agent.attributes or {}
    assert attributes["base14.filing.question_id"] == "q-oai-1"
    assert attributes["base14.gen_ai.model.digest"] == "6488c96fa5fa"
    assert named(spans, "execute_tool query_facts")


async def test_the_ranking_reply_reaches_the_analyst_with_the_frame_facts(
    facts: MemoryFacts,
) -> None:
    ranking_call = Call("rank_among_filers", {"input": "Workiva net_income 2024"})
    run = Run(facts, [ranking_call, ANSWER], [FRAME_CALL, Say("Ranked 5,000 of 6,060.")])
    await run()
    (reply,) = tool_outputs(run.analyst)
    assert "Ranked 5,000 of 6,060." in reply
    assert "Frame CY2024" in reply


async def test_the_call_budget_counts_both_agents(facts: MemoryFacts) -> None:
    run = Run(facts, [LOOKUP, LOOKUP, LOOKUP, ANSWER])
    with pytest.raises(BudgetExceeded):
        await run(call_budget=3)


async def test_the_budget_stop_names_its_error_type(facts: MemoryFacts) -> None:
    memory = captured_spans()
    with pytest.raises(BudgetExceeded):
        await Run(facts, [LOOKUP, LOOKUP, LOOKUP, ANSWER])(call_budget=3)
    (agent,) = named(memory.get_finished_spans(), "invoke_agent analyst")
    (event,) = [event for event in agent.events if event.name == "exception"]
    assert (event.attributes or {})["exception.type"] == "filing_analyst.budget.BudgetExceeded"


def test_optional_tool_parameters_are_not_required(facts: MemoryFacts) -> None:
    tools = bound_tools(Run(facts, []).context, ToolResultCollector())
    query, *_ = openai_tools(tools.analyst, CallBudget(10))
    assert isinstance(query, FunctionTool)
    assert query.params_json_schema["required"] == ["concept"]


async def test_a_stalled_model_times_out(facts: MemoryFacts) -> None:
    with pytest.raises(QuestionTimedOut):
        await Run(facts, [Stall()])(timeout_seconds=0.2)


async def test_an_unavailable_model_raises_a_connection_error(facts: MemoryFacts) -> None:
    with pytest.raises(ConnectionError):
        await Run(facts, [LOOKUP, ANSWER])(fault="model_unavailable")


async def test_bad_output_fails_validation(facts: MemoryFacts) -> None:
    with pytest.raises(BadOutput):
        await Run(facts, [LOOKUP, ANSWER])(fault="bad_output")


async def test_an_unknown_tool_is_bad_output(facts: MemoryFacts) -> None:
    with pytest.raises(BadOutput):
        await Run(facts, [Call("rank_among_filners", {"input": "x"})])()


async def test_a_list_sent_as_json_text_is_read(facts: MemoryFacts) -> None:
    answer = await Run(facts, [LOOKUP, Call("FilingAnswer", {**GOOD_ANSWER, "caveats": "[]"})])()
    assert answer.caveats == []


async def test_a_single_caveat_sent_as_text_is_a_list(facts: MemoryFacts) -> None:
    call = Call("FilingAnswer", {**GOOD_ANSWER, "caveats": "Fiscal 2019 only."})
    answer = await Run(facts, [LOOKUP, call])()
    assert answer.caveats == ["Fiscal 2019 only."]


async def test_an_answer_in_text_gets_one_reminder(facts: MemoryFacts) -> None:
    answer = await Run(facts, [LOOKUP, Say("Net income was -47.5M."), ANSWER])()
    assert answer.figures[0].accession == "0001445305-22-000041"


async def test_no_answer_tool_call_is_bad_output(facts: MemoryFacts) -> None:
    with pytest.raises(BadOutput):
        await Run(facts, [LOOKUP, Say("Net income was -47.5M.")])()


async def test_an_ungrounded_answer_cites_an_invented_accession(facts: MemoryFacts) -> None:
    run = Run(facts, [LOOKUP, ANSWER])
    answer = await run(fault="ungrounded_answer")
    assert answer.figures[0].accession == INVENTED_ACCESSION
    assert not verify_answer(answer, run.collector.results).passed


@pytest.mark.parametrize(("value", "mode"), [("true", "SPAN_ONLY"), ("false", "NO_CONTENT")])
def test_the_capture_setting_becomes_a_capture_mode(
    monkeypatch: pytest.MonkeyPatch, value: str, mode: str
) -> None:
    monkeypatch.setenv("OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT", value)
    apply_capture_mode()
    assert os.environ["OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"] == mode
