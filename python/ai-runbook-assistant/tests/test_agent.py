from langchain.agents import create_agent

from runbook_assistant.agent import AGENT_NAME, run_diagnosis
from runbook_assistant.tools import query_metrics
from tests.scripted_model import ScriptedChatModel, answer


def test_run_produces_a_named_invoke_agent_span(span_exporter):
    model = ScriptedChatModel(
        provider="ollama",
        model="qwen3.5:9B",
        script=[answer("checkout CPU is high; see runbook.", 10, 5)],
    )
    agent = create_agent(model=model, tools=[query_metrics], name=AGENT_NAME)

    run_diagnosis(agent, "why is checkout slow?", conversation_id="conv-1")

    agent_span = next(
        s for s in span_exporter.get_finished_spans() if s.name == f"invoke_agent {AGENT_NAME}"
    )
    assert agent_span.attributes["gen_ai.agent.name"] == AGENT_NAME
    assert agent_span.attributes["gen_ai.conversation.id"] == "conv-1"
