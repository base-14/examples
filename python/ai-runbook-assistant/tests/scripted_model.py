"""A chat model that answers, or fails, from a script, and reports a real provider and model.

The LangChain instrumentation reads the provider and model from the model's LangSmith
parameters, so this fake reports `ls_provider` and `ls_model_name` like a provider
integration does, and its answers carry `usage_metadata` and a finish reason.
"""

from typing import Any

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.language_models.base import LangSmithParams
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field


Step = dict[str, Any] | Exception


def answer(content: str, input_tokens: int, output_tokens: int) -> dict[str, Any]:
    return {"content": content, "input_tokens": input_tokens, "output_tokens": output_tokens}


class ScriptedChatModel(BaseChatModel):
    provider: str
    model: str
    script: list[Step] = Field(default_factory=list)
    calls: int = 0

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def _get_ls_params(self, stop: list[str] | None = None, **kwargs: Any) -> LangSmithParams:
        return LangSmithParams(
            ls_provider=self.provider, ls_model_name=self.model, ls_model_type="chat"
        )

    def bind_tools(self, tools: Any, **kwargs: Any) -> ScriptedChatModel:
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        step = self.script[self.calls]
        self.calls += 1
        if isinstance(step, Exception):
            raise step
        message = AIMessage(
            content=step["content"],
            usage_metadata={
                "input_tokens": step["input_tokens"],
                "output_tokens": step["output_tokens"],
                "total_tokens": step["input_tokens"] + step["output_tokens"],
            },
            response_metadata={"model_name": self.model, "finish_reason": "stop"},
        )
        return ChatResult(
            generations=[ChatGeneration(message=message, generation_info={"finish_reason": "stop"})]
        )
