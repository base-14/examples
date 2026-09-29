import asyncio
from typing import Any

import httpx
import pytest
from opentelemetry.trace import StatusCode

from filing_analyst.agents import (
    ANALYST_NAME,
    RANKING_NAME,
    BadOutput,
    QuestionTimedOut,
)
from filing_analyst.budget import BudgetExceeded
from filing_analyst.frameworks.strands import StrandsFramework, strands_tools
from filing_analyst.model_faults import INVENTED_ACCESSION
from filing_analyst.telemetry import COST_ATTRIBUTE
from filing_analyst.tools import ToolContext, bound_tools
from filing_analyst.verifier import ToolResultCollector, verify_answer
from tests.agent_support import (
    ANALYST_MODEL,
    GOOD_ANSWER,
    LOOKUP,
    NI_2019,
    RANKING_MODEL,
    Call,
    Say,
    Stall,
    config,
    request,
)
from tests.scripted_model import ScriptedModel, tool_results
from tests.sec_support import FakeClock, RecordingHandler, sec_client
from tests.span_capture import captured_spans, named, only
from tests.test_tools import FRAME
from tests.tools_support import AIRBNB, WORKIVA, MemoryFacts


ANSWER = Call("FilingAnswer", GOOD_ANSWER)


@pytest.fixture(scope="module")
def facts() -> MemoryFacts:
    return MemoryFacts.of(WORKIVA)


class Run:
    def __init__(
        self, facts: MemoryFacts, analyst: list[Any], ranking: list[Any] | None = None
    ) -> None:
        self.analyst = ScriptedModel(ANALYST_MODEL, analyst)
        self.ranking = ScriptedModel(RANKING_MODEL, ranking or [])
        self.collector = ToolResultCollector()
        self.frames = RecordingHandler(lambda _r: httpx.Response(200, json=FRAME))
        self.context = ToolContext(
            facts=facts, sec=sec_client(self.frames, FakeClock()), cik=WORKIVA
        )

    def model(self, model_id: str) -> ScriptedModel:
        return self.analyst if model_id == ANALYST_MODEL else self.ranking

    async def __call__(self, **changes: Any) -> Any:
        return await StrandsFramework(self.model).run(
            request(**changes), config(), self.context, self.collector
        )


async def test_the_analyst_returns_the_typed_answer(facts: MemoryFacts) -> None:
    run = Run(facts, [LOOKUP, ANSWER])
    answer = await run()
    assert answer.figures[0].accession == "0001445305-22-000041"
    assert run.collector.results[0]["rows"][0]["value"] == -47479000
    assert verify_answer(answer, run.collector.results).passed


async def test_a_validation_failure_goes_back_to_the_model_as_a_tool_error(
    facts: MemoryFacts,
) -> None:
    bad = {**GOOD_ANSWER, "figures": [{**NI_2019, "accession": "not-an-accession"}]}
    run = Run(facts, [LOOKUP, Call("FilingAnswer", bad), ANSWER])
    answer = await run()
    assert answer.figures[0].accession == NI_2019["accession"]
    assert [r["status"] for r in tool_results(run.analyst)][-1] == "error"


async def test_two_turns_without_the_answer_tool_raise(facts: MemoryFacts) -> None:
    run = Run(facts, [LOOKUP, Say("Net income was -47.5M."), Say("As I said.")])
    with pytest.raises(BadOutput):
        await run()


async def test_the_call_budget_counts_both_agents(facts: MemoryFacts) -> None:
    rank = Call("rank_among_filers", {"input": "Rank WORKIVA INC on net_income for 2024."})
    frame = Call("frame_values", {"concept": "net_income", "year": 2024})
    run = Run(facts, [rank, ANSWER], [frame, frame, frame, Say("Ranked.")])
    with pytest.raises(BudgetExceeded) as raised:
        await run(call_budget=5)
    assert raised.value.model_calls + raised.value.tool_calls == 6
    assert len(run.ranking.seen) >= 2


async def test_the_wall_clock_budget_cancels_the_run(facts: MemoryFacts) -> None:
    run = Run(facts, [LOOKUP, ANSWER])
    with pytest.raises(QuestionTimedOut):
        await run(fault="slow_model", timeout_seconds=0.2)


async def test_a_model_call_that_ignores_the_cancel_signal_still_times_out(
    facts: MemoryFacts, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("filing_analyst.agents.TIMEOUT_GRACE_SECONDS", 0.1)
    memory = captured_spans()
    run = Run(facts, [Stall()])
    with pytest.raises(QuestionTimedOut):
        await asyncio.wait_for(run(timeout_seconds=0.2), timeout=5)
    assert named(memory.get_finished_spans(), f"invoke_agent {ANALYST_NAME}")


async def test_model_unavailable_raises_a_connection_error(facts: MemoryFacts) -> None:
    run = Run(facts, [LOOKUP, ANSWER])
    with pytest.raises(ConnectionError):
        await run(fault="model_unavailable")
    assert run.analyst.seen == []


async def test_bad_output_fails_validation_then_raises(facts: MemoryFacts) -> None:
    run = Run(facts, [LOOKUP, ANSWER, ANSWER, ANSWER])
    with pytest.raises(BadOutput):
        await run(fault="bad_output")


async def test_ungrounded_answer_carries_an_invented_accession(facts: MemoryFacts) -> None:
    run = Run(facts, [LOOKUP, ANSWER])
    answer = await run(fault="ungrounded_answer")
    assert answer.figures[0].accession == INVENTED_ACCESSION
    assert verify_answer(answer, run.collector.results).reason == "accession_not_in_run"


async def test_the_trace_of_a_ranking_question(facts: MemoryFacts) -> None:
    memory = captured_spans()
    rank = Call("rank_among_filers", {"input": "Rank WORKIVA INC on net_income for 2024."})
    frame = Call("frame_values", {"concept": "net_income", "year": 2024})
    run = Run(facts, [rank, ANSWER], [frame, Say("Workiva ranks 17 of 20.")])
    run.context = ToolContext(facts=facts, sec=run.context.sec, cik=AIRBNB)
    await run()
    spans = memory.get_finished_spans()
    by_id = {span.context.span_id: span for span in spans if span.context}

    analyst = only(spans, f"invoke_agent {ANALYST_NAME}")
    ranking = only(spans, f"invoke_agent {RANKING_NAME}")
    rank_tool = only(spans, "execute_tool rank_among_filers")
    assert ranking.parent is not None and by_id[ranking.parent.span_id] is rank_tool
    assert only(spans, "execute_tool frame_values").status.status_code != StatusCode.ERROR
    assert named(spans, "execute_event_loop_cycle")

    chats = named(spans, "chat")
    assert len(chats) == 4
    for span in [analyst, ranking, *chats, rank_tool]:
        attributes = span.attributes or {}
        assert attributes["gen_ai.conversation.id"] == "q-test-1"
        assert attributes["base14.filing.question_id"] == "q-test-1"
        assert attributes["base14.filing.ticker"] == "WK"
        assert attributes["base14.filing.cik"] == WORKIVA
        assert attributes["gen_ai.provider.name"] == "ollama"
        assert attributes["server.address"] == "ollama.test"
        assert attributes["server.port"] == 11434
    for chat in chats:
        attributes = chat.attributes or {}
        assert attributes[COST_ATTRIBUTE] == 0.0
        assert attributes["gen_ai.usage.input_tokens"] == 120

    analyst_attributes = analyst.attributes or {}
    assert analyst_attributes["base14.prompt.version"] == config().analyst_prompt.version
    assert analyst_attributes["base14.gen_ai.model.digest"] == "6488c96fa5fa"
    assert analyst_attributes["base14.filing.fixture_date"] == "2026-09-26"
    assert (ranking.attributes or {})["base14.gen_ai.model.digest"] == "7fbdbf8f5e45"


async def test_a_timed_out_run_ends_without_error_status(facts: MemoryFacts) -> None:
    memory = captured_spans()
    run = Run(facts, [LOOKUP, ANSWER])
    with pytest.raises(QuestionTimedOut):
        await run(fault="slow_model", timeout_seconds=0.2)
    agent_span = only(memory.get_finished_spans(), f"invoke_agent {ANALYST_NAME}")
    assert agent_span.status.status_code != StatusCode.ERROR


async def test_a_budget_stop_ends_the_agent_span_with_error(facts: MemoryFacts) -> None:
    memory = captured_spans()
    run = Run(facts, [LOOKUP, LOOKUP, LOOKUP, ANSWER])
    with pytest.raises(BudgetExceeded):
        await run(call_budget=2)
    agent_span = only(memory.get_finished_spans(), f"invoke_agent {ANALYST_NAME}")
    assert agent_span.status.status_code == StatusCode.ERROR
    assert (agent_span.attributes or {})["error.type"] == "filing_analyst.budget.BudgetExceeded"


async def test_a_budget_stop_on_a_tool_call_still_exports_its_span(facts: MemoryFacts) -> None:
    memory = captured_spans()
    run = Run(facts, [LOOKUP, ANSWER])
    with pytest.raises(BudgetExceeded) as raised:
        await run(call_budget=1)
    assert (raised.value.model_calls, raised.value.tool_calls) == (1, 1)
    tool_span = only(memory.get_finished_spans(), "execute_tool query_facts")
    assert tool_span.status.status_code == StatusCode.ERROR
    assert (tool_span.attributes or {})["error.type"] == "filing_analyst.budget.BudgetExceeded"
    assert len(named(memory.get_finished_spans(), "chat")) == 1


def test_the_strands_tools_carry_their_names_and_docs(facts: MemoryFacts) -> None:
    run = Run(facts, [])
    tools = bound_tools(run.context, run.collector)
    specs = {
        t.tool_spec["name"]: t.tool_spec for t in strands_tools([*tools.analyst, *tools.ranking])
    }
    assert set(specs) == {"query_facts", "compute_ratio", "frame_values"}
    assert "total_liabilities" in specs["query_facts"]["description"]
    assert "Args" not in specs["query_facts"]["description"]
    assert set(specs["query_facts"]["inputSchema"]["json"]["properties"]) == {
        "concept",
        "fiscal_year_from",
        "fiscal_year_to",
    }
