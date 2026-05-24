"""SME-v1 -> OTLP bridge.

Subscribes to the device telemetry and offline (Last Will) topics, parses
the compact JSON envelope a constrained device publishes, and emits OTel
metrics, logs, and spans per device. Malformed or unknown-version frames
are counted and dropped, never fatal.
"""

from __future__ import annotations

import json
import logging
import os
import signal
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion

from telemetry import BridgeTelemetry

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("sme-bridge")

BROKER_HOST = os.getenv("MQTT_HOST", "mosquitto")
BROKER_PORT = int(os.getenv("MQTT_PORT", "1883"))
TOPIC_PREFIX = os.getenv("TOPIC_PREFIX", "scout/mcu").rstrip("/")
HEALTH_PORT = int(os.getenv("HEALTH_PORT", "8080"))
SUPPORTED_VERSIONS = {1}

tel = BridgeTelemetry()
ready = threading.Event()


def _resource_attrs(device: dict) -> dict:
    attrs = {"device.id": device.get("id"), "device.kind": "mcu"}
    if "model" in device:
        attrs["device.model.identifier"] = device["model"]
    firmware = device.get("firmware", {})
    if "version" in firmware:
        attrs["device.firmware.version"] = firmware["version"]
    if "channel" in firmware:
        attrs["device.firmware.channel"] = firmware["channel"]
    fleet = device.get("fleet", {})
    if "id" in fleet:
        attrs["fleet.id"] = fleet["id"]
    if "tenant" in fleet:
        attrs["fleet.tenant"] = fleet["tenant"]
    return attrs


def _handle_telemetry(env: dict) -> None:
    version = env.get("v")
    if version not in SUPPORTED_VERSIONS:
        log.warning("rejecting envelope version %s", version)
        tel.count_version_rejected(version)
        return

    device = env.get("device") or {}
    device_id = device.get("id")
    if not device_id:
        tel.count_parse_error()
        return

    dev = tel.device(device_id, _resource_attrs(device))
    point_attrs = {}
    if env.get("ts_source"):
        point_attrs["mcu.ts_source"] = env["ts_source"]

    for metric in env.get("metrics") or []:
        dev.record_metric(
            metric["name"],
            metric.get("kind", "gauge"),
            metric["value"],
            metric.get("unit", ""),
            dict(point_attrs),
        )

    for event in env.get("events") or []:
        attrs = dict(event.get("attrs") or {})
        dev.emit_event(event["name"], event.get("severity", "info"), attrs)

    trace = env.get("trace") or {}
    if trace.get("traceparent"):
        dev.trace_publish(trace["traceparent"], dict(point_attrs))

    tel.count_message("ok")


def _handle_offline(env: dict) -> None:
    device = env.get("device") or {}
    device_id = device.get("id")
    if not device_id:
        return
    dev = tel.device(device_id, _resource_attrs(device))
    dev.emit_event(
        "device offline", "error", {"reason": env.get("reason", "lwt")}
    )
    log.warning("device offline: %s", device_id)


def _on_connect(client, _userdata, _flags, reason_code, _props) -> None:
    if reason_code != 0:
        log.error("connect failed: %s", reason_code)
        return
    client.subscribe(f"{TOPIC_PREFIX}/+/telemetry", qos=1)
    client.subscribe(f"{TOPIC_PREFIX}/+/offline", qos=1)
    ready.set()
    log.info("connected; subscribed under %s/+", TOPIC_PREFIX)


def _on_message(_client, _userdata, msg) -> None:
    try:
        env = json.loads(msg.payload)
    except (ValueError, TypeError):
        log.warning("unparseable payload on %s", msg.topic)
        tel.count_parse_error()
        return
    try:
        if msg.topic.endswith("/offline"):
            _handle_offline(env)
        else:
            _handle_telemetry(env)
    except Exception:  # noqa: BLE001 - one bad frame must not kill the loop
        log.exception("failed to handle message on %s", msg.topic)
        tel.count_parse_error()


class _Health(BaseHTTPRequestHandler):
    def do_GET(self):
        ok = ready.is_set()
        self.send_response(200 if ok else 503)
        self.end_headers()
        self.wfile.write(b"ok" if ok else b"starting")

    def log_message(self, *_args):
        pass


def _serve_health() -> None:
    HTTPServer(("0.0.0.0", HEALTH_PORT), _Health).serve_forever()


def main() -> None:
    threading.Thread(target=_serve_health, daemon=True).start()

    client = mqtt.Client(
        CallbackAPIVersion.VERSION2, client_id="sme-bridge", protocol=mqtt.MQTTv5
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
