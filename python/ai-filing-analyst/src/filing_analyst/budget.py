"""A call budget shared by both agents of one question.

Strands' native `limits` count one agent and end the run without error status. This hook counts
model and tool calls across the analyst and the ranking agent. Past the limit, a model call raises,
which ends `invoke_agent` with error status. A tool call is cancelled instead, because Strands
never ends the `execute_tool` span when a tool hook raises; the next model call raises.
"""

import logging
import threading
from typing import Any

from opentelemetry import trace
from strands.hooks import BeforeModelCallEvent, BeforeToolCallEvent, HookProvider, HookRegistry

from filing_analyst.telemetry import ERROR_TYPE_ATTRIBUTE


logger = logging.getLogger(__name__)


class BudgetExceeded(Exception):
    def __init__(self, limit: int, model_calls: int, tool_calls: int) -> None:
        super().__init__(
            f"call budget of {limit} spent: {model_calls} model calls, {tool_calls} tool calls"
        )
        self.limit = limit
        self.model_calls = model_calls
        self.tool_calls = tool_calls


BUDGET_ERROR_TYPE = f"{BudgetExceeded.__module__}.{BudgetExceeded.__qualname__}"


class CallBudget(HookProvider):
    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.model_calls = 0
        self.tool_calls = 0
        self.exceeded: BudgetExceeded | None = None
        self._lock = threading.Lock()

    def register_hooks(self, registry: HookRegistry, **kwargs: Any) -> None:
        registry.add_callback(BeforeModelCallEvent, self._on_model_call)
        registry.add_callback(BeforeToolCallEvent, self._on_tool_call)

    def _on_model_call(self, event: BeforeModelCallEvent) -> None:
        exceeded = self._count(model=True)
        if exceeded is not None:
            raise exceeded

    def _on_tool_call(self, event: BeforeToolCallEvent) -> None:
        exceeded = self._count(model=False)
        if exceeded is not None:
            trace.get_current_span().set_attribute(ERROR_TYPE_ATTRIBUTE, BUDGET_ERROR_TYPE)
            event.cancel_tool = str(exceeded)

    def _count(self, *, model: bool) -> BudgetExceeded | None:
        """The first stop is sticky. The ranking agent runs as a tool, and a tool's failure goes
        back to the analyst as a tool result, so the analyst's next call raises the same stop."""
        with self._lock:
            if self.exceeded is None:
                if model:
                    self.model_calls += 1
                else:
                    self.tool_calls += 1
                if self.model_calls + self.tool_calls > self.limit:
                    self.exceeded = BudgetExceeded(self.limit, self.model_calls, self.tool_calls)
                    logger.warning(
                        "Call budget of %d spent: %d model calls, %d tool calls",
                        self.limit,
                        self.model_calls,
                        self.tool_calls,
                    )
            return self.exceeded
