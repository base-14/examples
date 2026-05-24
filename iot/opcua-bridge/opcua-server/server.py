"""asyncua OPC-UA server that stands in for factory-floor equipment.

It exposes a small address space - a pump, a conveyor, an oven, and a
production line - under the `http://factory-demo` namespace (index 2), then
runs the simulator loop in the same event loop so the node values move. No
security and anonymous access: this is a local demo, not a production server.
"""

from __future__ import annotations

import asyncio
import logging
import os

from asyncua import Server, ua

from simulator import run_simulation

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("opcua-server")

ENDPOINT = os.getenv("OPCUA_ENDPOINT", "opc.tcp://0.0.0.0:4840/factory/")
NAMESPACE = "http://factory-demo"


async def main() -> None:
    server = Server()
    await server.init()
    server.set_endpoint(ENDPOINT)
    server.set_server_name("Factory Demo OPC-UA Server")
    server.set_security_policy([ua.SecurityPolicyType.NoSecurity])

    idx = await server.register_namespace(NAMESPACE)
    objects = server.nodes.objects

    pump = await objects.add_object(idx, "Pump1")
    conveyor = await objects.add_object(idx, "Conveyor1")
    oven = await objects.add_object(idx, "Oven1")
    line = await objects.add_object(idx, "Line1")

    nodes = {
        "flow": await pump.add_variable(ua.NodeId("Pump1/Flow", idx), "Flow", 50.0),
        "status": await pump.add_variable(
            ua.NodeId("Pump1/Status", idx), "Status", "running"
        ),
        "vibration": await pump.add_variable(
            ua.NodeId("Pump1/VibrationRMS", idx), "VibrationRMS", 2.5
        ),
        "speed": await conveyor.add_variable(
            ua.NodeId("Conveyor1/SpeedRPM", idx), "SpeedRPM", 1200.0
        ),
        "temp": await oven.add_variable(ua.NodeId("Oven1/TempC", idx), "TempC", 165.0),
        "throughput": await line.add_variable(
            ua.NodeId("Line1/ThroughputCounter", idx),
            "ThroughputCounter",
            ua.Variant(0, ua.VariantType.UInt64),
        ),
    }

    async with server:
        log.info("OPC-UA server up at %s (ns=%s '%s')", ENDPOINT, idx, NAMESPACE)
        await run_simulation(nodes)


if __name__ == "__main__":
    asyncio.run(main())
