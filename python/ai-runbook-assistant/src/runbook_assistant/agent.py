"""LangChain 1.x tool-calling agent (LangGraph-backed) for SRE diagnosis."""

from typing import Any

from langchain.agents import create_agent

from runbook_assistant.llm import build_models
from runbook_assistant.telemetry.genai_spans import RunAttributes, run_attributes
from runbook_assistant.tools import build_tools


SYSTEM_PROMPT = (
    "You are an SRE assistant. Diagnose the incident by following a runbook: "
    "first call search_runbooks to find the relevant procedure, then follow its "
    "diagnostic steps in order, using query_metrics, search_logs, and "
    "get_service_status to gather evidence before you conclude. Base your "
    "root-cause and remediation on that evidence and cite the runbook(s) you "
    "used. Be concise and actionable."
)


AGENT_NAME = "runbook_assistant"


def build_agent(retriever: Any) -> Any:
    model, resilience = build_models()
    return create_agent(
        model=model,
        tools=build_tools(retriever),
        system_prompt=SYSTEM_PROMPT,
        middleware=[resilience],
        name=AGENT_NAME,
    )


def run_diagnosis(agent: Any, question: str, conversation_id: str) -> str:
    """The instrumentation reads the conversation ID from the run's metadata."""
    with run_attributes(RunAttributes(conversation_id=conversation_id)):
        result = agent.invoke(
            {"messages": [{"role": "user", "content": question}]},
            config={"metadata": {"conversation_id": conversation_id}},
        )
    messages = result.get("messages", [])
    return messages[-1].content if messages else ""
