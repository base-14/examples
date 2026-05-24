"""Downstream HTTP echo service.

Auto-instrumented FastAPI (via opentelemetry-instrument). The consumer's
instrumented requests call carries the trace context here, so the inbound
span shares trace_id with the producer and consumer spans, demonstrating that
context survives the whole producer -> MQTT -> consumer -> HTTP path.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("echo")

app = FastAPI(title="mqtt-trace-echo")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/echo")
async def echo(request: Request) -> dict[str, object]:
    body = await request.json()
    log.info("echo received message_id=%s", body.get("message_id"))
    return {"echoed": body}
