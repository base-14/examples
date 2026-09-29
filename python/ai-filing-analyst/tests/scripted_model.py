import asyncio
import copy
import json
from collections.abc import AsyncGenerator
from typing import Any

from strands.models.model import Model
from strands.types.content import Messages
from strands.types.streaming import StreamEvent
from strands.types.tools import ToolSpec

from tests.agent_support import Call, Say, Stall, Turn


ANALYST_MODEL = "qwen3.5:9B"
RANKING_MODEL = "gemma4:e2b"
USAGE = {"inputTokens": 120, "outputTokens": 30, "totalTokens": 150}


class ScriptedModel(Model):
    """Plays back one turn per model call: a tool call or a closing text. Once the script
    runs out it ends every turn with text."""

    def __init__(self, model_id: str, turns: list[Turn]) -> None:
        self.config: dict[str, Any] = {"model_id": model_id}
        self.turns = list(turns)
        self.seen: list[Messages] = []

    def update_config(self, **model_config: Any) -> None:
        self.config.update(model_config)

    def get_config(self) -> dict[str, Any]:
        return self.config

    async def structured_output(self, *args: Any, **kwargs: Any) -> AsyncGenerator[Any]:
        raise NotImplementedError
        yield

    async def stream(
        self,
        messages: Messages,
        tool_specs: list[ToolSpec] | None = None,
        system_prompt: str | None = None,
        **kwargs: Any,
    ) -> AsyncGenerator[StreamEvent]:
        self.seen.append(copy.deepcopy(messages))
        turn = self.turns.pop(0) if self.turns else Say("Done.")
        if isinstance(turn, Stall):
            await asyncio.Event().wait()
        yield {"messageStart": {"role": "assistant"}}
        if isinstance(turn, Call):
            yield {
                "contentBlockStart": {
                    "start": {"toolUse": {"name": turn.name, "toolUseId": f"t{len(self.seen)}"}}
                }
            }
            yield {"contentBlockDelta": {"delta": {"toolUse": {"input": json.dumps(turn.input)}}}}
            yield {"contentBlockStop": {}}
            yield {"messageStop": {"stopReason": "tool_use"}}
        else:
            yield {"contentBlockStart": {"start": {}}}
            yield {"contentBlockDelta": {"delta": {"text": turn.text}}}
            yield {"contentBlockStop": {}}
            yield {"messageStop": {"stopReason": "end_turn"}}
        yield {"metadata": {"usage": USAGE, "metrics": {"latencyMs": 5}}}  # type: ignore[typeddict-item]


def tool_results(model: ScriptedModel) -> list[dict[str, Any]]:
    """Every tool result block the model was shown, from its last call."""
    return [
        block["toolResult"]
        for message in model.seen[-1]
        for block in message["content"]
        if "toolResult" in block
    ]


class Scripts:
    """One scripted analyst and one scripted ranking model per question, from turn lists."""

    def __init__(self, analyst: list[Any], ranking: list[Any] | None = None) -> None:
        self.analyst = ScriptedModel(ANALYST_MODEL, analyst)
        self.ranking = ScriptedModel(RANKING_MODEL, ranking or [])

    def __call__(self, model_id: str) -> ScriptedModel:
        return self.analyst if model_id == ANALYST_MODEL else self.ranking
