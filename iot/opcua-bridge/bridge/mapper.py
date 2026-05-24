"""Turns node_map.yaml into OTel observable instruments backed by a shared
value cache that the OPC-UA subscription handler keeps up to date.

Each gauge/counter entry becomes an observable instrument whose callback reads
the latest value for its node out of the cache at collection time. `status`
entries are not metrics; their node IDs and attributes are returned so the
handler can log fault transitions.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from opentelemetry.metrics import CallbackOptions, Meter, Observation


def load_node_map(path: str) -> list[dict]:
    return yaml.safe_load(Path(path).read_text())["nodes"]


def _callback(node_id: str, attributes: dict, cache: dict):
    def cb(_options: CallbackOptions):
        value = cache.get(node_id)
        if value is None:
            return []
        return [Observation(float(value), attributes)]

    return cb


def build(meter: Meter, node_map: list[dict], cache: dict) -> tuple[list[str], dict]:
    subscribe_ids: list[str] = []
    status_nodes: dict[str, dict] = {}

    for entry in node_map:
        node_id = entry["node_id"]
        subscribe_ids.append(node_id)
        metric = entry.get("metric", {})
        attributes = entry.get("attributes", {})
        kind = metric.get("kind")

        if kind == "status":
            status_nodes[node_id] = attributes
            continue

        callback = _callback(node_id, attributes, cache)
        name = metric["name"]
        unit = metric.get("unit", "")
        description = metric.get("description", "")
        if kind == "counter":
            meter.create_observable_counter(
                name, callbacks=[callback], unit=unit, description=description
            )
        else:
            meter.create_observable_gauge(
                name, callbacks=[callback], unit=unit, description=description
            )

    return subscribe_ids, status_nodes
