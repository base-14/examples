from runbook_assistant.telemetry.metrics import GenAIMetrics


def test_instruments_record_without_error():
    m = GenAIMetrics()
    attrs = {"gen_ai.operation.name": "chat", "gen_ai.provider.name": "anthropic"}
    m.record_tokens(attrs, 10, 5)
    m.record_duration(attrs, 0.5)
    m.add_cost(attrs, 0.0001)
    m.add_error({**attrs, "error.type": "Timeout"})
