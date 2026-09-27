"""Model failures injected on demand, behind `FILING_FAULTS_ENABLED`.

The wrapper sits between the analyst agent and its Ollama model, so Strands instruments the
failures as it would real ones.
"""

import asyncio
import json
import threading
from collections.abc import AsyncGenerator, AsyncIterable
from enum import StrEnum
from typing import Any

from strands.models.model import Model
from strands.types.streaming import StreamEvent


INVENTED_ACCESSION = "0000000000-00-000000"
INVALID_ACCESSION = "not-an-accession"
SLOW_MODEL_SECONDS = 60.0
SLOW_MODEL_POLL_SECONDS = 0.05


class ModelFault(StrEnum):
    MODEL_UNAVAILABLE = "model_unavailable"
    SLOW_MODEL = "slow_model"
    BAD_OUTPUT = "bad_output"
    UNGROUNDED_ANSWER = "ungrounded_answer"


def _invalid(answer: dict[str, Any]) -> dict[str, Any]:
    figures = answer.get("figures") or [{}]
    return {**answer, "figures": [{**figures[0], "accession": INVALID_ACCESSION}]}


def _ungrounded(answer: dict[str, Any]) -> dict[str, Any]:
    figures = answer.get("figures") or [
        {"concept": "revenue", "value": 1.0, "unit": "USD", "fiscal_year": 2024, "form": "10-K"}
    ]
    return {**answer, "figures": [{**f, "accession": INVENTED_ACCESSION} for f in figures]}


def _starts_tool(event: StreamEvent, name: str) -> bool:
    start: dict[str, Any] = dict(event.get("contentBlockStart", {}).get("start", {}))
    return bool(start.get("toolUse", {}).get("name") == name)


def _closing_text(text: str) -> list[StreamEvent]:
    return [
        {"messageStart": {"role": "assistant"}},
        {"contentBlockStart": {"start": {}}},
        {"contentBlockDelta": {"delta": {"text": text}}},
        {"contentBlockStop": {}},
        {"messageStop": {"stopReason": "end_turn"}},
    ]


class FaultInjectingModel(Model):
    """`model_unavailable` raises a connection error on the first call. `slow_model` waits
    before each call until the question's cancel signal fires. `bad_output` makes the first
    answer tool call fail validation and every later turn end without it. `ungrounded_answer`
    swaps the answer's accession numbers for one no tool returned."""

    def __init__(
        self,
        inner: Model,
        fault: ModelFault,
        answer_tool: str,
        slow_seconds: float = SLOW_MODEL_SECONDS,
    ) -> None:
        self._inner = inner
        self._fault = fault
        self._answer_tool = answer_tool
        self._slow_seconds = slow_seconds
        self._answer_rewritten = False

    @property
    def config(self) -> Any:
        return getattr(self._inner, "config", {})

    def update_config(self, **model_config: Any) -> None:
        self._inner.update_config(**model_config)

    def get_config(self) -> Any:
        return self._inner.get_config()

    async def structured_output(self, *args: Any, **kwargs: Any) -> AsyncGenerator[Any]:
        async for event in self._inner.structured_output(*args, **kwargs):
            yield event

    async def stream(self, *args: Any, **kwargs: Any) -> AsyncGenerator[StreamEvent]:
        if self._fault == ModelFault.MODEL_UNAVAILABLE:
            raise ConnectionError("Failed to connect to Ollama (injected model_unavailable)")
        if self._fault == ModelFault.SLOW_MODEL:
            await self._wait(kwargs.get("cancel_signal"))
        if self._fault == ModelFault.BAD_OUTPUT and self._answer_rewritten:
            for event in _closing_text("I could not produce the answer."):
                yield event
            return
        async for event in self._rewrite_answer(self._inner.stream(*args, **kwargs)):
            yield event

    async def _wait(self, cancel_signal: threading.Event | None) -> None:
        waited = 0.0
        while waited < self._slow_seconds and not (cancel_signal and cancel_signal.is_set()):
            await asyncio.sleep(SLOW_MODEL_POLL_SECONDS)
            waited += SLOW_MODEL_POLL_SECONDS

    async def _rewrite_answer(
        self, events: AsyncIterable[StreamEvent]
    ) -> AsyncGenerator[StreamEvent]:
        rewriting = False
        buffered: list[str] = []
        async for event in events:
            if _starts_tool(event, self._answer_tool):
                rewriting = self._fault in (ModelFault.BAD_OUTPUT, ModelFault.UNGROUNDED_ANSWER)
                rewriting = rewriting and not self._answer_rewritten
            elif rewriting and "contentBlockDelta" in event:
                buffered.append(
                    event["contentBlockDelta"]["delta"].get("toolUse", {}).get("input", "")
                )
                continue
            elif rewriting and "contentBlockStop" in event:
                answer = json.loads("".join(buffered) or "{}")
                changed = (
                    _invalid(answer)
                    if self._fault == ModelFault.BAD_OUTPUT
                    else _ungrounded(answer)
                )
                yield {"contentBlockDelta": {"delta": {"toolUse": {"input": json.dumps(changed)}}}}
                rewriting = False
                self._answer_rewritten = True
            yield event
