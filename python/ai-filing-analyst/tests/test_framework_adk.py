import asyncio
import os
from collections.abc import AsyncGenerator
from typing import Any

import httpx
import pytest
from google.adk.models._capabilities import LlmCapabilities
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import types
from pydantic import Field

from filing_analyst.agents import BadOutput, QuestionTimedOut
from filing_analyst.budget import BudgetExceeded
from filing_analyst.frameworks.adk import AdkFramework, apply_capture_setting
from filing_analyst.model_faults import INVENTED_ACCESSION
from filing_analyst.tools import ToolContext
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


ANSWER = Call("set_model_response", GOOD_ANSWER)
USAGE = types.GenerateContentResponseUsageMetadata(
    prompt_token_count=120, candidates_token_count=30, total_token_count=150
)


class ScriptedLlm(BaseLlm):
    """Plays back one turn per model call, like LiteLLM without a native output schema."""

    turns: list[Any] = Field(default_factory=list)
    seen: list[LlmRequest] = Field(default_factory=list)

    @property
    def capabilities(self) -> LlmCapabilities:
        return LlmCapabilities(output_schema_and_tools=False)

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse]:
        self.seen.append(llm_request)
        turn: Turn = self.turns.pop(0) if self.turns else Say("Done.")
        if isinstance(turn, Stall):
            await asyncio.Event().wait()
        if isinstance(turn, Call):
            part = types.Part(function_call=types.FunctionCall(name=turn.name, args=turn.input))
        else:
            part = types.Part(text=turn.text)
        yield LlmResponse(content=types.Content(role="model", parts=[part]), usage_metadata=USAGE)


def function_responses(model: ScriptedLlm) -> list[dict[str, Any]]:
    """Every tool result the model was shown, from its last call."""
    return [
        part.function_response.response or {}
        for content in model.seen[-1].contents
        for part in content.parts or []
        if part.function_response
    ]


@pytest.fixture(scope="module")
def facts() -> MemoryFacts:
    return MemoryFacts.of(WORKIVA)


class Run:
    def __init__(
        self, facts: MemoryFacts, analyst: list[Any], ranking: list[Any] | None = None
    ) -> None:
        self.analyst = ScriptedLlm(model=ANALYST_MODEL, turns=analyst)
        self.ranking = ScriptedLlm(model=RANKING_MODEL, turns=ranking or [])
        self.collector = ToolResultCollector()
        self.frames = RecordingHandler(lambda _r: httpx.Response(200, json=FRAME))
        self.context = ToolContext(
            facts=facts, sec=sec_client(self.frames, FakeClock()), cik=WORKIVA
        )

    def model(self, model_id: str) -> ScriptedLlm:
        return self.analyst if model_id == ANALYST_MODEL else self.ranking

    async def __call__(self, **changes: Any) -> Any:
        return await AdkFramework(self.model).run(
            request(**changes), config(), self.context, self.collector
        )


async def test_the_analyst_returns_the_typed_answer(facts: MemoryFacts) -> None:
    run = Run(facts, [LOOKUP, ANSWER])
    answer = await run()
    assert answer.figures[0].accession == "0001445305-22-000041"
    assert run.collector.results[0]["rows"][0]["value"] == -47479000
    assert verify_answer(answer, run.collector.results).passed


async def test_the_answer_tool_is_offered_last(facts: MemoryFacts) -> None:
    run = Run(facts, [LOOKUP, ANSWER])
    await run()
    tools = run.analyst.seen[0].config.tools or []
    names = [
        d.name for t in tools if isinstance(t, types.Tool) for d in t.function_declarations or []
    ]
    assert names[-1] == "set_model_response"
    assert "query_facts" in names


async def test_the_spans_carry_the_question_attributes(facts: MemoryFacts) -> None:
    memory = captured_spans()
    await Run(facts, [LOOKUP, ANSWER])(question_id="q-adk-1")
    spans = memory.get_finished_spans()
    (agent,) = named(spans, "invoke_agent analyst")
    attributes = agent.attributes or {}
    assert attributes["gen_ai.conversation.id"] == "q-adk-1"
    assert attributes["base14.filing.question_id"] == "q-adk-1"
    assert attributes["base14.gen_ai.model.digest"] == "6488c96fa5fa"
    assert named(spans, "execute_tool query_facts")


async def test_the_ranking_reply_reaches_the_analyst_with_the_frame_facts(
    facts: MemoryFacts,
) -> None:
    ranking_call = Call("rank_among_filers", {"request": "Workiva net_income 2024"})
    run = Run(facts, [ranking_call, ANSWER], [FRAME_CALL, Say("Ranked 5,000 of 6,060.")])
    await run()
    (reply,) = [r for r in function_responses(run.analyst) if "result" in r]
    assert "Ranked 5,000 of 6,060." in reply["result"]
    assert "Frame CY2024" in reply["result"]


async def test_the_call_budget_counts_both_agents(facts: MemoryFacts) -> None:
    run = Run(facts, [LOOKUP, LOOKUP, LOOKUP, ANSWER])
    with pytest.raises(BudgetExceeded):
        await run(call_budget=3)


async def test_a_stalled_model_times_out(facts: MemoryFacts) -> None:
    with pytest.raises(QuestionTimedOut):
        await Run(facts, [Stall()])(timeout_seconds=0.2)


async def test_an_unavailable_model_raises_a_connection_error(facts: MemoryFacts) -> None:
    with pytest.raises(ConnectionError):
        await Run(facts, [LOOKUP, ANSWER])(fault="model_unavailable")


async def test_bad_output_fails_validation(facts: MemoryFacts) -> None:
    with pytest.raises(BadOutput):
        await Run(facts, [LOOKUP, ANSWER])(fault="bad_output")


async def test_no_typed_answer_is_bad_output(facts: MemoryFacts) -> None:
    with pytest.raises(BadOutput):
        await Run(facts, [LOOKUP, Say("Net income was -47.5M.")])()


async def test_an_ungrounded_answer_cites_an_invented_accession(facts: MemoryFacts) -> None:
    run = Run(facts, [LOOKUP, ANSWER])
    answer = await run(fault="ungrounded_answer")
    assert answer.figures[0].accession == INVENTED_ACCESSION
    assert not verify_answer(answer, run.collector.results).passed


@pytest.mark.parametrize("value", ["true", "false"])
def test_adk_span_capture_follows_the_standard_setting(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT", value)
    monkeypatch.delenv("ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS", raising=False)
    apply_capture_setting()
    assert os.environ["ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS"] == value
