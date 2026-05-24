"""Deserialize W3C trace context from MQTT 5 user properties.

The mirror of the producer side: take the user-property list off the received
PUBLISH and hand it to the W3C propagator as a dict carrier, yielding a Context
whose parent is the producer's span.
"""

from __future__ import annotations

from opentelemetry.context import Context
from opentelemetry.propagate import extract

UserProperties = list[tuple[str, str]] | None


def user_properties_to_context(user_property: UserProperties) -> Context:
    carrier = dict(user_property or [])
    return extract(carrier)


def has_trace_context(user_property: UserProperties) -> bool:
    return any(key == "traceparent" for key, _ in (user_property or []))
