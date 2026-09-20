"""Zero-code LangChain instrumentation via OpenLLMetry (Traceloop).

`opentelemetry-instrumentation-langchain` patches
langchain_core.callbacks.BaseCallbackManager.__init__ to inject its own callback
handler, the same mechanism the custom handler uses.

The package ships `opentelemetry-semantic-conventions-ai`, whose attribute names
overlap with but are not identical to the OTel GenAI conventions. Check the
captured spans before relying on a name.
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
