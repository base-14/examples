"""OPC-UA -> OTLP bridge.

Subscribes to the OPC-UA nodes named in node_map.yaml, caches their values,
and exposes them as OTLP metrics through observable callbacks. A pump status
transition to "fault" is emitted as an OTLP log record carrying the asset
attributes. The session is wrapped in an `opcua.session` span: a server
restart ends that span, the bridge reconnects with exponential backoff, and a
new session span begins - so reconnects are visible as a sequence of spans.
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal

from asyncua import Client
from opentelemetry import metrics, trace
from opentelemetry._logs import get_logger_provider
from opentelemetry.trace import SpanKind

from mapper import build, load_node_map
from telemetry import setup_telemetry

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
# asyncua logs each publish callback at INFO, which dumps full payloads; the
# bridge's own logs are the signal here.
logging.getLogger("asyncua").setLevel(logging.WARNING)
log = logging.getLogger("opcua-bridge")

ENDPOINT = os.getenv("OPCUA_ENDPOINT", "opc.tcp://opcua-server:4840/factory/")
NODE_MAP_PATH = os.getenv("NODE_MAP_PATH", "node_map.yaml")
SUB_INTERVAL_MS = int(os.getenv("OPCUA_SUB_INTERVAL_MS", "500"))

cache: dict = {}
_running = True


class SubHandler:
    """Caches every data change and logs pump status transitions."""

    def __init__(self, status_nodes: dict, bridge_log: logging.Logger):
        self._status_nodes = status_nodes
        self._log = bridge_log
        self._last: dict = {}

    def datachange_notification(self, node, val, _data):
        node_id = node.nodeid.to_string()
        cache[node_id] = val
        if node_id in self._status_nodes and val != self._last.get(node_id):
            previous = self._last.get(node_id)
            self._last[node_id] = val
            attributes = dict(self._status_nodes[node_id])
            attributes["asset.status"] = val
            if val == "fault":
                self._log.warning("asset entered fault state", extra=attributes)
            elif previous is not None:
                self._log.info("asset recovered", extra=attributes)


async def _serve() -> None:
    tracer, meter, bridge_log = setup_telemetry()
    subscribe_ids, status_nodes = build(meter, load_node_map(NODE_MAP_PATH), cache)
    handler = SubHandler(status_nodes, bridge_log)
    backoff = 1

    while _running:
        try:
            async with Client(ENDPOINT) as client:
                backoff = 1
                with tracer.start_as_current_span(
                    "opcua.session", kind=SpanKind.CLIENT
                ) as span:
                    span.set_attribute("opcua.endpoint", ENDPOINT)
                    span.set_attribute("opcua.security_policy", "None")
                    log.info("connected to %s", ENDPOINT)
                    subscription = await client.create_subscription(
                        SUB_INTERVAL_MS, handler
                    )
                    await subscription.subscribe_data_change(
                        [client.get_node(node_id) for node_id in subscribe_ids]
                    )
                    while _running:
                        await asyncio.sleep(3)
                        await client.get_node(subscribe_ids[0]).read_value()
        except Exception as exc:  # noqa: BLE001 - reconnect on any session failure
            if not _running:
                break
            log.warning("opcua session ended: %s; reconnecting in %ss", exc, backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30)

    trace.get_tracer_provider().shutdown()
    metrics.get_meter_provider().shutdown()
    get_logger_provider().shutdown()


def _stop(*_args) -> None:
    global _running
    _running = False


def main() -> None:
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    asyncio.run(_serve())


if __name__ == "__main__":
    main()
