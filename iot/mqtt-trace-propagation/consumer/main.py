"""Subscribes to sensor readings, continues the producer's trace, and makes an
instrumented HTTP call to the echo service so the trace visibly flows past the
MQTT hop into a normal request span.

The broker (Mosquitto) is not instrumented and stays "dark" in the trace; that
is fine because the endpoints propagate context, so producer and consumer spans
share one trace_id with no gap that matters.
"""

from __future__ import annotations

import json
import logging
import os
import signal

import paho.mqtt.client as mqtt
import requests
from opentelemetry import trace
from opentelemetry.trace import SpanKind

from propagation import has_trace_context, user_properties_to_context
from telemetry import setup_telemetry

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("consumer")

BROKER_HOST = os.getenv("MQTT_BROKER_HOST", "mosquitto")
BROKER_PORT = int(os.getenv("MQTT_BROKER_PORT", "1883"))
TOPIC_FILTER = os.getenv("MQTT_TOPIC_FILTER", "sensors/+/reading")
ECHO_URL = os.getenv("ECHO_URL", "http://echo:8000/echo")

tracer, meter = setup_telemetry()
readings_processed = meter.create_counter(
    "iot.readings.processed", unit="{reading}", description="Sensor readings processed"
)


def on_connect(client, userdata, flags, reason_code, properties):  # noqa: ARG001
    client.subscribe(TOPIC_FILTER, qos=1)
    log.info("consumer subscribed to %s", TOPIC_FILTER)


def on_message(client, userdata, message):  # noqa: ARG001
    user_props = getattr(message.properties, "UserProperty", None)
    topic = message.topic

    attributes = {
        "messaging.system": "mqtt",
        "messaging.destination.name": topic,
        "messaging.operation.type": "process",
    }

    if has_trace_context(user_props):
        parent = user_properties_to_context(user_props)
        span = tracer.start_span(
            f"process {topic}", context=parent, kind=SpanKind.CONSUMER, attributes=attributes
        )
    else:
        attributes["mqtt.missing_context"] = True
        span = tracer.start_span(f"process {topic}", kind=SpanKind.CONSUMER, attributes=attributes)
        log.warning("message on %s had no trace context; started a new root span", topic)

    with trace.use_span(span, end_on_exit=True):
        try:
            payload = json.loads(message.payload)
            span.set_attribute("messaging.message.id", payload.get("message_id", ""))
        except (ValueError, TypeError):
            payload = {"raw": message.payload.decode("utf-8", "replace")}

        resp = requests.post(ECHO_URL, json=payload, timeout=5)
        resp.raise_for_status()
        readings_processed.add(1, {"messaging.destination.name": topic})
        trace_id = trace.format_trace_id(span.get_span_context().trace_id)
        log.info("processed message on %s trace_id=%s -> echo %s", topic, trace_id, resp.status_code)


def main() -> None:
    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id="consumer-1",
        protocol=mqtt.MQTTv5,
    )
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(BROKER_HOST, BROKER_PORT)

    running = {"v": True}
    signal.signal(signal.SIGTERM, lambda *_: running.update(v=False))
    signal.signal(signal.SIGINT, lambda *_: running.update(v=False))

    client.loop_start()
    try:
        while running["v"]:
            signal.pause()
    finally:
        client.loop_stop()
        client.disconnect()
        trace.get_tracer_provider().shutdown()


if __name__ == "__main__":
    main()
