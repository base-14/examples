"""Sparkplug B -> OTLP decoder.

Subscribes to `spBv1.0/#`, decodes each protobuf payload, tracks edge-node and
device lifecycle, resolves DATA aliases against the metric definitions seen at
BIRTH, and emits OTel metrics + lifecycle log records to the collector.
"""

from __future__ import annotations

import logging
import os
import signal
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion

import sparkplug_b_pb2 as sp
from state import MetricDef, SparkplugState
from telemetry import DecoderTelemetry

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("decoder")

BROKER_HOST = os.getenv("MQTT_HOST", "mosquitto")
BROKER_PORT = int(os.getenv("MQTT_PORT", "1883"))
TOPIC = os.getenv("SPB_TOPIC", "spBv1.0/#")
HEALTH_PORT = int(os.getenv("HEALTH_PORT", "8080"))

_INT_DATATYPES = {
    sp.Int8, sp.Int16, sp.Int32, sp.Int64,
    sp.UInt8, sp.UInt16, sp.UInt32, sp.UInt64,
}

state = SparkplugState()
tel = DecoderTelemetry()
ready = threading.Event()  # set once subscribed, so /healthz gates the simulator


def _metric_value(metric):
    field = metric.WhichOneof("value")
    return getattr(metric, field) if field else None


def _node_attrs(edge_node: str) -> dict:
    return {"asset.id": edge_node, "asset.type": "sparkplug_edge_node"}


def _device_attrs(edge_node: str, device: str) -> dict:
    return {
        "asset.id": device,
        "asset.type": "sparkplug_device",
        "asset.parent_id": edge_node,
    }


def _defs_from_birth(payload) -> dict[int, MetricDef]:
    defs: dict[int, MetricDef] = {}
    for m in payload.metrics:
        if m.HasField("alias"):
            defs[m.alias] = MetricDef(name=m.name, datatype=m.datatype)
    return defs


def _record_birth_values(payload, edge_node: str, device: str) -> None:
    attrs = _device_attrs(edge_node, device)
    for m in payload.metrics:
        value = _metric_value(m)
        if value is None:
            continue
        tel.record(m.name, value, m.datatype in _INT_DATATYPES, attrs)


def _handle_data(payload, group: str, edge_node: str, device: str) -> None:
    if state.check_seq(group, edge_node, payload.seq):
        log.warning("seq gap on %s/%s/%s", group, edge_node, device)
        tel.count_seq_gap(_device_attrs(edge_node, device))
    attrs = _device_attrs(edge_node, device)
    for m in payload.metrics:
        if not m.HasField("alias"):
            continue
        definition = state.resolve(group, edge_node, device, m.alias)
        if definition is None:
            log.warning("unresolved alias %s on %s/%s", m.alias, edge_node, device)
            tel.count_unresolved(attrs)
            continue
        value = _metric_value(m)
        if value is not None:
            tel.record(
                definition.name, value, definition.datatype in _INT_DATATYPES, attrs
            )


def _dispatch(topic: str, raw: bytes) -> None:
    parts = topic.split("/")
    if len(parts) < 4:
        return
    _, group, msg_type, edge_node, *rest = parts
    device = rest[0] if rest else None
    tel.count_message(msg_type)

    payload = sp.Payload()
    payload.ParseFromString(raw)

    if msg_type == "NBIRTH":
        bd_seq = next(
            (m.long_value for m in payload.metrics if m.name == "bdSeq"), None
        )
        state.node_birth(group, edge_node, _defs_from_birth(payload), bd_seq)
        log.info("NBIRTH %s/%s bdSeq=%s", group, edge_node, bd_seq)
        tel.lifecycle("edge node online", dead=False, attrs=_node_attrs(edge_node))
    elif msg_type == "DBIRTH" and device:
        state.check_seq(group, edge_node, payload.seq)
        state.device_birth(group, edge_node, device, _defs_from_birth(payload))
        _record_birth_values(payload, edge_node, device)
        log.info("DBIRTH %s/%s/%s", group, edge_node, device)
        tel.lifecycle(
            "device online", dead=False, attrs=_device_attrs(edge_node, device)
        )
    elif msg_type == "DDATA" and device:
        _handle_data(payload, group, edge_node, device)
    elif msg_type == "DDEATH" and device:
        state.check_seq(group, edge_node, payload.seq)
        state.device_death(group, edge_node, device)
        log.info("DDEATH %s/%s/%s", group, edge_node, device)
        tel.lifecycle(
            "device offline", dead=True, attrs=_device_attrs(edge_node, device)
        )
    elif msg_type == "NDEATH":
        state.node_death(group, edge_node)
        log.info("NDEATH %s/%s", group, edge_node)
        tel.lifecycle("edge node offline", dead=True, attrs=_node_attrs(edge_node))


def _on_connect(client, _userdata, _flags, reason_code, _props) -> None:
    if reason_code != 0:
        log.error("connect failed: %s", reason_code)
        return
    client.subscribe(TOPIC, qos=0)
    ready.set()
    log.info("connected; subscribed to %s", TOPIC)


def _on_message(_client, _userdata, msg) -> None:
    try:
        _dispatch(msg.topic, msg.payload)
    except Exception:  # noqa: BLE001 - one bad frame must not kill the loop
        log.exception("failed to decode message on %s", msg.topic)


class _Health(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/healthz":
            self.send_response(404)
        else:
            # Healthy only once subscribed, so the simulator's BIRTHs are not
            # published before the decoder is listening (late-subscriber race).
            self.send_response(200 if ready.is_set() else 503)
        self.end_headers()
        self.wfile.write(b"ok" if ready.is_set() else b"starting")

    def log_message(self, *_args):
        pass


def _serve_health() -> None:
    HTTPServer(("0.0.0.0", HEALTH_PORT), _Health).serve_forever()


def main() -> None:
    threading.Thread(target=_serve_health, daemon=True).start()

    client = mqtt.Client(
        CallbackAPIVersion.VERSION2, client_id="sparkplug-decoder", protocol=mqtt.MQTTv5
    )
    client.on_connect = _on_connect
    client.on_message = _on_message

    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())

    client.connect(BROKER_HOST, BROKER_PORT)
    client.loop_start()
    stop.wait()

    client.loop_stop()
    tel.shutdown()


if __name__ == "__main__":
    main()
