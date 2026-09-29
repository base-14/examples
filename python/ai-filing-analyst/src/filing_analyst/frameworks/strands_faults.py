"""The Strands wrapper that injects model failures between the analyst agent and its Ollama
model, so Strands instruments them as it would real ones."""

import asyncio
import json
import threading
from collections.abc import AsyncGenerator, AsyncIterable
from typing import Any

from strands.models.model import Model
from strands.types.streaming import StreamEvent

from filing_analyst.model_faults import (
    SLOW_MODEL_POLL_SECONDS,
    SLOW_MODEL_SECONDS,
    ModelFault,
    invalid_answer,
    ungrounded_answer,
)


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
                    invalid_answer(answer)
                    if self._fault == ModelFault.BAD_OUTPUT
                    else ungrounded_answer(answer)
                )
                yield {"contentBlockDelta": {"delta": {"toolUse": {"input": json.dumps(changed)}}}}
                rewriting = False
                self._answer_rewritten = True
            yield event
