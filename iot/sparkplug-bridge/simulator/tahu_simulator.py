"""Sparkplug B simulator: one edge node (FactoryA/EdgeNode1) with two
devices (Machine1, Machine2).

Publishes the Sparkplug lifecycle by hand so the wire format is explicit:
NBIRTH with a bdSeq metric, a DBIRTH per device advertising every metric
with a name+alias, then DDATA every second carrying alias-only values. The
edge-node `seq` counter increments on every payload (0-255, wrapping). A
Last Will is registered so the broker emits NDEATH if the simulator drops.

Two knobs exercise the decoder:
  DEVICE_CYCLE_S  - every N seconds, send DDEATH then DBIRTH for Machine2.
  DROP_EVERY_N    - drop every Nth DDATA (seq still advances) to force a gap.
"""

from __future__ import annotations

import math
import os
import random
import time

import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion

import sparkplug_b_pb2 as sp

BROKER_HOST = os.getenv("MQTT_HOST", "mosquitto")
BROKER_PORT = int(os.getenv("MQTT_PORT", "1883"))
GROUP_ID = os.getenv("SPB_GROUP_ID", "FactoryA")
EDGE_NODE_ID = os.getenv("SPB_EDGE_NODE_ID", "EdgeNode1")
DEVICE_CYCLE_S = int(os.getenv("DEVICE_CYCLE_S", "300"))
DROP_EVERY_N = int(os.getenv("DROP_EVERY_N", "0"))

DEVICES = ["Machine1", "Machine2"]

# Per-device metric definitions: name -> (alias, datatype). Aliases are
# globally unique here for clarity; Sparkplug only requires uniqueness per
# edge node.
_METRICS = {
    "Machine1": {
        "Temperature": (1, sp.Double),
        "Throughput": (2, sp.Int64),
        "RunState": (3, sp.Boolean),
        "VibrationRMS": (4, sp.Double),
    },
    "Machine2": {
        "Temperature": (5, sp.Double),
        "Throughput": (6, sp.Int64),
        "RunState": (7, sp.Boolean),
        "VibrationRMS": (8, sp.Double),
    },
}


def _now_ms() -> int:
    return int(time.time() * 1000)


def _set_value(metric, datatype, value) -> None:
    if datatype in (sp.Double, sp.Float):
        metric.double_value = float(value)
    elif datatype in (sp.Int64, sp.UInt64, sp.Int32, sp.UInt32):
        metric.long_value = int(value)
    elif datatype == sp.Boolean:
        metric.boolean_value = bool(value)
    else:
        metric.string_value = str(value)


class Simulator:
    def __init__(self) -> None:
        self.seq = 0
        self.bd_seq = 0
        self.throughput = {d: 0 for d in DEVICES}
        self.ddata_count = 0
        self.client = mqtt.Client(
            CallbackAPIVersion.VERSION2,
            client_id=f"{GROUP_ID}-{EDGE_NODE_ID}",
            protocol=mqtt.MQTTv5,
        )
        self.client.on_connect = self._on_connect

    def _topic(self, msg_type: str, device: str | None = None) -> str:
        base = f"spBv1.0/{GROUP_ID}/{msg_type}/{EDGE_NODE_ID}"
        return f"{base}/{device}" if device else base

    def _next_seq(self) -> int:
        s = self.seq
        self.seq = (self.seq + 1) % 256
        return s

    def _publish(self, topic: str, payload: sp.Payload, qos: int = 0) -> None:
        self.client.publish(topic, payload.SerializeToString(), qos=qos)

    def _ndeath_payload(self) -> bytes:
        # The Last Will: a bare bdSeq so a host can match it to our NBIRTH.
        payload = sp.Payload()
        m = payload.metrics.add()
        m.name = "bdSeq"
        m.datatype = sp.UInt64
        m.long_value = self.bd_seq
        return payload.SerializeToString()

    def _node_birth(self) -> None:
        self.seq = 0  # NBIRTH resets the edge-node sequence to 0.
        payload = sp.Payload()
        payload.timestamp = _now_ms()
        payload.seq = self._next_seq()
        m = payload.metrics.add()
        m.name = "bdSeq"
        m.datatype = sp.UInt64
        m.long_value = self.bd_seq
        self._publish(self._topic("NBIRTH"), payload, qos=1)

    def _device_birth(self, device: str) -> None:
        payload = sp.Payload()
        payload.timestamp = _now_ms()
        payload.seq = self._next_seq()
        for name, (alias, datatype) in _METRICS[device].items():
            m = payload.metrics.add()
            m.name = name
            m.alias = alias
            m.timestamp = _now_ms()
            m.datatype = datatype
            _set_value(m, datatype, self._reading(device, name))
        self._publish(self._topic("DBIRTH", device), payload, qos=1)

    def _device_death(self, device: str) -> None:
        payload = sp.Payload()
        payload.timestamp = _now_ms()
        payload.seq = self._next_seq()
        self._publish(self._topic("DDEATH", device), payload, qos=1)

    def _device_data(self, device: str) -> None:
        self.ddata_count += 1
        payload = sp.Payload()
        payload.timestamp = _now_ms()
        seq = self._next_seq()
        payload.seq = seq
        for name, (alias, datatype) in _METRICS[device].items():
            m = payload.metrics.add()
            m.alias = alias  # DDATA references metrics by alias only.
            m.timestamp = _now_ms()
            _set_value(m, datatype, self._reading(device, name))
        if DROP_EVERY_N > 0 and self.ddata_count % DROP_EVERY_N == 0:
            # Build and advance seq, but never send: a real gap on the wire.
            print(f"[sim] dropping DDATA for {device} seq={seq} (forced gap)")
            return
        self._publish(self._topic("DDATA", device), payload)

    def _reading(self, device: str, name: str):
        if name == "Temperature":
            return round(70 + 10 * math.sin(time.time() / 30) + random.uniform(-2, 2), 2)
        if name == "Throughput":
            self.throughput[device] += random.randint(1, 5)
            return self.throughput[device]
        if name == "RunState":
            return True
        if name == "VibrationRMS":
            return round(random.uniform(1.5, 4.0), 3)
        return 0

    def _on_connect(self, client, _userdata, _flags, reason_code, _props) -> None:
        if reason_code != 0:
            print(f"[sim] connect failed: {reason_code}")
            return
        print(f"[sim] connected; NBIRTH for {GROUP_ID}/{EDGE_NODE_ID} (bdSeq={self.bd_seq})")
        self._node_birth()
        for device in DEVICES:
            self._device_birth(device)

    def run(self) -> None:
        self.client.will_set(
            self._topic("NDEATH"), self._ndeath_payload(), qos=1, retain=False
        )
        self.client.connect(BROKER_HOST, BROKER_PORT)
        self.client.loop_start()

        last_cycle = time.time()
        cycling = DEVICE_CYCLE_S > 0
        while True:
            time.sleep(1)
            for device in DEVICES:
                self._device_data(device)
            if cycling and time.time() - last_cycle >= DEVICE_CYCLE_S:
                last_cycle = time.time()
                print("[sim] cycling Machine2: DDEATH then DBIRTH")
                self._device_death("Machine2")
                time.sleep(2)
                self._device_birth("Machine2")


if __name__ == "__main__":
    Simulator().run()
