"""Simulated sensor: publishes a reading every 2s to MQTT 5, injecting W3C
trace context into the PUBLISH user properties so the consumer can continue
the same trace.

The producer span is opened before publish and closed on PUBACK (QoS 1), so
its duration reflects the real broker round-trip. A mid -> span map correlates
the asynchronous PUBACK callback back to the span that started the publish.
"""

from __future__ import annotations

import json
import logging
import os
import random
import signal
import time
import uuid

import paho.mqtt.client as mqtt
from opentelemetry import trace
from opentelemetry.trace import SpanKind
from paho.mqtt.packettypes import PacketTypes
from paho.mqtt.properties import Properties

from propagation import context_to_user_properties
from telemetry import setup_telemetry

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("producer")

BROKER_HOST = os.getenv("MQTT_BROKER_HOST", "mosquitto")
BROKER_PORT = int(os.getenv("MQTT_BROKER_PORT", "1883"))
DEVICE_ID = os.getenv("DEVICE_ID", "sensor-001")
TOPIC = f"sensors/{DEVICE_ID}/reading"
PUBLISH_INTERVAL_S = float(os.getenv("PUBLISH_INTERVAL_S", "2"))

tracer, meter = setup_telemetry()
readings_published = meter.create_counter(
    "iot.readings.published", unit="{reading}", description="Sensor readings published"
)

# Spans opened at publish, closed on PUBACK. Keyed by MQTT message id.
_pending: dict[int, trace.Span] = {}
_running = True


def on_publish(client, userdata, mid, reason_code, properties):  # noqa: ARG001
    span = _pending.pop(mid, None)
    if span is not None:
        span.end()


def _publish_reading(client: mqtt.Client) -> None:
    message_id = str(uuid.uuid4())
    span = tracer.start_span(
        f"publish {TOPIC}",
        kind=SpanKind.PRODUCER,
        attributes={
            "messaging.system": "mqtt",
            "messaging.destination.name": TOPIC,
            "messaging.operation.type": "publish",
            "messaging.message.id": message_id,
        },
    )
    ctx = trace.set_span_in_context(span)

    props = Properties(PacketTypes.PUBLISH)
    props.UserProperty = context_to_user_properties(ctx)

    payload = json.dumps(
        {
            "device_id": DEVICE_ID,
            "reading": round(random.uniform(18.0, 26.0), 2),
            "message_id": message_id,
            "ts": time.time(),
        }
    )
    info = client.publish(TOPIC, payload, qos=1, properties=props)
    _pending[info.mid] = span
    readings_published.add(1, {"device.id": DEVICE_ID})
    trace_id = trace.format_trace_id(span.get_span_context().trace_id)
    log.info("published reading mid=%s trace_id=%s", info.mid, trace_id)


def _stop(*_args) -> None:
    global _running
    _running = False


def main() -> None:
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"producer-{DEVICE_ID}",
        protocol=mqtt.MQTTv5,
    )
    client.on_publish = on_publish
    client.connect(BROKER_HOST, BROKER_PORT)
    client.loop_start()
    log.info("producer connected to %s:%s, publishing to %s", BROKER_HOST, BROKER_PORT, TOPIC)

    try:
        while _running:
            _publish_reading(client)
            time.sleep(PUBLISH_INTERVAL_S)
    finally:
        client.loop_stop()
        client.disconnect()
        for span in _pending.values():
            span.end()
        trace.get_tracer_provider().shutdown()


if __name__ == "__main__":
    main()
