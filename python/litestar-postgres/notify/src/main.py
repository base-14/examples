"""Notification microservice.

Receives `POST /notify` from `litestar-postgres-app` whenever an article is
created. Returns 200 immediately — production systems would enqueue this onto
SNS/Kafka/etc. The point of this service in the example is to demonstrate
distributed tracing: the inbound HTTP span here should share `trace_id` with
the outbound httpx span on the article side.
"""

import logging

import msgspec
from litestar import Controller, Litestar, get, post
from litestar.contrib.opentelemetry import OpenTelemetryConfig, OpenTelemetryPlugin

from src.logging_config import build_logging_config
from src.telemetry import notifications_received

logger = logging.getLogger(__name__)


class NotifyPayload(msgspec.Struct):
    article_id: int
    title: str


class HealthController(Controller):
    path = "/health"

    @get("/")
    async def health(self) -> dict[str, str]:
        return {"status": "ok", "service": "litestar-postgres-notify"}


class NotifyController(Controller):
    path = "/notify"

    @post("/", status_code=200)
    async def notify(self, data: NotifyPayload) -> dict[str, object]:
        notifications_received.add(1)
        logger.info(
            "article notification received",
            extra={"article_id": data.article_id, "title": data.title},
        )
        return {"received": True, "article_id": data.article_id}


app = Litestar(
    route_handlers=[HealthController, NotifyController],
    plugins=[OpenTelemetryPlugin(config=OpenTelemetryConfig())],
    logging_config=build_logging_config(),
)
