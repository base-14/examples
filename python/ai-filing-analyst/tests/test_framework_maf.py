import asyncio
from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from ollama import ChatResponse, Message

from filing_analyst.agents import BadOutput, QuestionTimedOut
from filing_analyst.budget import BudgetExceeded
from filing_analyst.frameworks.maf import MafFramework, ollama_clients
from filing_analyst.model_faults import INVENTED_ACCESSION
from filing_analyst.tools import ToolContext
from filing_analyst.verifier import ToolResultCollector, verify_answer
from tests.agent_support import (
    ANALYST_MODEL,
    FRAME_CALL,
    GOOD_ANSWER,
    LOOKUP,
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


class ScriptedOllama:
    """Stands in for the Ollama client: one turn per chat call, by model."""

    def __init__(self, analyst: list[Any], ranking: list[Any]) -> None:
        self.turns = {ANALYST_MODEL: list(analyst)}
        self.ranking = list(ranking)
        self.seen: dict[str, list[list[Any]]] = {}
        self._client = SimpleNamespace(base_url="http://ollama.test:11434")

    async def chat(self, *, model: str, messages: list[Any], stream: bool = False, **_: Any) -> Any:
        self.seen.setdefault(model, []).append(messages)
        turns = self.turns.get(model, self.ranking)
        turn: Turn = turns.pop(0) if turns else Say("Done.")
        if isinstance(turn, Stall):
            await asyncio.Event().wait()
        if isinstance(turn, Call):
            call = Message.ToolCall(
                function=Message.ToolCall.Function(name=turn.name, arguments=turn.input)
            )
            message = Message(role="assistant", content="", tool_calls=[call])
        else:
            message = Message(role="assistant", content=turn.text)
        response = ChatResponse(
            model=model,
            message=message,
            done=True,
            done_reason="stop",
            prompt_eval_count=120,
            eval_count=30,
        )
        return _streamed(response) if stream else response


async def _streamed(response: ChatResponse) -> AsyncIterator[ChatResponse]:
    yield response


def tool_messages(ollama: ScriptedOllama) -> list[str]:
    """Every tool result the analyst was shown, from its last call."""
    return [
        str(message.get("content"))
        for message in ollama.seen[ANALYST_MODEL][-1]
        if message.get("role") == "tool"
    ]


@pytest.fixture(scope="module")
def facts() -> MemoryFacts:
    return MemoryFacts.of(WORKIVA)


class Run:
    def __init__(
        self, facts: MemoryFacts, analyst: list[Any], ranking: list[Any] | None = None
    ) -> None:
        self.ollama = ScriptedOllama(analyst, ranking or [])
        self.collector = ToolResultCollector()
        self.frames = RecordingHandler(lambda _r: httpx.Response(200, json=FRAME))
        self.context = ToolContext(
            facts=facts, sec=sec_client(self.frames, FakeClock()), cik=WORKIVA
        )

    async def __call__(self, **changes: Any) -> Any:
        clients = ollama_clients("http://ollama.test:11434", self.ollama)  # type: ignore[arg-type]
        return await MafFramework(clients, think=False).run(
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
    await Run(facts, [LOOKUP, ANSWER])(question_id="q-maf-1")
    spans = memory.get_finished_spans()
    (agent,) = named(spans, "invoke_agent analyst")
    attributes = agent.attributes or {}
    assert attributes["base14.filing.question_id"] == "q-maf-1"
    assert attributes["base14.gen_ai.model.digest"] == "6488c96fa5fa"
    assert named(spans, "execute_tool query_facts")


async def test_the_ranking_reply_reaches_the_analyst_with_the_frame_facts(
    facts: MemoryFacts,
) -> None:
    ranking_call = Call("rank_among_filers", {"task": "Workiva net_income 2024"})
    run = Run(facts, [ranking_call, ANSWER], [FRAME_CALL, Say("Ranked 5,000 of 6,060.")])
    await run()
    (reply,) = tool_messages(run.ollama)
    assert "Ranked 5,000 of 6,060." in reply
    assert "Frame CY2024" in reply


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
