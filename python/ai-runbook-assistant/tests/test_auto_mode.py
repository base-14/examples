def test_enable_auto_instrumentation_idempotent():
    from opentelemetry.instrumentation.langchain import LangchainInstrumentor

    from runbook_assistant.telemetry import auto

    try:
        auto.enable_auto_instrumentation()
        auto.enable_auto_instrumentation()
    finally:
        # Don't leak the global BaseCallbackManager monkeypatch into other tests.
        LangchainInstrumentor().uninstrument()
        auto._enabled = False
