"""Serialize W3C trace context into MQTT 5 user properties.

MQTT 5 user properties are a list of (key, value) string pairs on the PUBLISH
packet. The W3C TraceContext propagator writes into a plain dict carrier, so
the bridge is just turning that dict into the user-property list the broker
carries to the consumer.
"""

from __future__ import annotations

from opentelemetry.context import Context
from opentelemetry.propagate import inject


def context_to_user_properties(
    context: Context | None = None,
) -> list[tuple[str, str]]:
    """Return MQTT 5 user properties carrying the trace context.

    With no argument, the currently active context is used.
    """
    carrier: dict[str, str] = {}
    inject(carrier, context=context)
    return list(carrier.items())
