"""LangChain 1.x tool-calling agent (LangGraph-backed) for SRE diagnosis."""

from typing import Any

from langchain.agents import create_agent

from runbook_assistant.llm import build_chat_model
from runbook_assistant.tools import build_tools


SYSTEM_PROMPT = (
    "You are an SRE assistant. Diagnose the incident by following a runbook: "
    "first call search_runbooks to find the relevant procedure, then follow its "
    "diagnostic steps in order, using query_metrics, search_logs, and "
    "get_service_status to gather evidence before you conclude. Base your "
    "root-cause and remediation on that evidence and cite the runbook(s) you "
    "used. Be concise and actionable."
)


def build_agent(retriever: Any) -> Any:
    return create_agent(
        model=build_chat_model(),
        tools=build_tools(retriever),
        system_prompt=SYSTEM_PROMPT,
    )


def run_diagnosis(agent: Any, question: str, callbacks: list[Any] | None = None) -> str:
    result = agent.invoke(
        {"messages": [{"role": "user", "content": question}]},
        config={"callbacks": callbacks or []},
    )
    messages = result.get("messages", [])
    return messages[-1].content if messages else ""
