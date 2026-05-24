"""Mutates the OPC-UA node values on a schedule so the bridge has live data.

Pump flow follows a slow sine with noise, the oven temperature a slower sine,
and the throughput counter climbs monotonically. Every FAULT_INTERVAL_S the
pump is driven into a fault for FAULT_DURATION_S: status flips to "fault",
flow and conveyor speed drop to zero, and vibration spikes - giving the bridge
something worth logging.
"""

from __future__ import annotations

import asyncio
import logging
import math
import os
import random
import time

from asyncua import ua

log = logging.getLogger("simulator")

UPDATE_MS = int(os.getenv("UPDATE_INTERVAL_MS", "500"))
FAULT_INTERVAL_S = int(os.getenv("FAULT_INTERVAL_S", "600"))
FAULT_DURATION_S = int(os.getenv("FAULT_DURATION_S", "30"))


async def run_simulation(nodes: dict) -> None:
    t0 = time.monotonic()
    counter = 0
    fault_until = 0.0
    next_fault = t0 + FAULT_INTERVAL_S

    while True:
        now = time.monotonic()
        elapsed = now - t0

        if now < fault_until:
            in_fault = True
        elif now >= next_fault:
            fault_until = now + FAULT_DURATION_S
            next_fault = now + FAULT_INTERVAL_S + FAULT_DURATION_S
            in_fault = True
            log.info("injecting pump fault for %ss", FAULT_DURATION_S)
        else:
            in_fault = False

        if in_fault:
            flow, status, speed = 0.0, "fault", 0.0
            vibration = round(8.0 + random.uniform(-1.0, 1.0), 2)
        else:
            flow = round(50 + 10 * math.sin(elapsed / 5) + random.uniform(-1, 1), 2)
            status = "running"
            speed = round(1200 + random.uniform(-20, 20), 1)
            vibration = round(2.5 + random.uniform(-0.3, 0.3), 2)
            counter += random.randint(1, 3)

        temp = round(165 + 15 * math.sin(elapsed / 30), 2)

        await nodes["flow"].write_value(flow)
        await nodes["status"].write_value(status)
        await nodes["vibration"].write_value(vibration)
        await nodes["speed"].write_value(speed)
        await nodes["temp"].write_value(temp)
        await nodes["throughput"].write_value(ua.Variant(counter, ua.VariantType.UInt64))

        await asyncio.sleep(UPDATE_MS / 1000)
