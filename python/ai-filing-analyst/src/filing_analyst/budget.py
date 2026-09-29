"""A call budget shared by both agents of one question.

Each framework's hooks call `count_model` before a model call and `count_tool` before a tool
call, across the analyst and the ranking agent. Past the limit, `count_model` raises, which ends
`invoke_agent` with error status. `count_tool` returns the stop instead, so the hook can cancel
the tool in the way its framework allows; the next model call raises.
"""

import logging
import threading


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


class CallBudget:
    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.model_calls = 0
        self.tool_calls = 0
        self.exceeded: BudgetExceeded | None = None
        self._lock = threading.Lock()

    def count_model(self) -> None:
        exceeded = self._count(model=True)
        if exceeded is not None:
            raise exceeded

    def count_tool(self) -> BudgetExceeded | None:
        return self._count(model=False)

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
