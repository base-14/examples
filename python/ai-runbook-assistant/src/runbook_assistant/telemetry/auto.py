"""Zero-code LangChain instrumentation via OpenLLMetry (Traceloop).

`opentelemetry-instrumentation-langchain` monkeypatches
langchain_core.callbacks.BaseCallbackManager.__init__ to auto-inject a callback
handler — i.e. the same mechanism the custom handler uses, done for you.

NOTE (build-time): the PyPI name `opentelemetry-instrumentation-langchain` is
Traceloop's package. It ships `opentelemetry-semantic-conventions-ai`, so the
exact attribute names overlap but are NOT identical to OTel GenAI v1.40.0 —
verify against captured spans.
"""

import logging


logger = logging.getLogger(__name__)
_enabled = False


def enable_auto_instrumentation() -> None:
    global _enabled
    if _enabled:
        return
    from opentelemetry.instrumentation.langchain import LangchainInstrumentor

    LangchainInstrumentor().instrument()
    _enabled = True
    logger.info("OpenLLMetry LangChain auto-instrumentation enabled")
