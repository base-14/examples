"""Litestar application entry point.

`create_app()` is a factory so tests can build fresh app instances bound to a
SQLite test DB without leaking state. `app` (module-level) is what
`uvicorn src.main:app` boots in production.

OpenTelemetry note: tracing/metrics/logs are wired in by the
`opentelemetry-instrument` CLI wrapper (see Dockerfile CMD). The wrapper reads
`OTEL_*` env vars, installs the ASGI middleware, and patches SQLAlchemy +
httpx + asyncpg. No SDK calls are needed in this file for Phase 2.
"""

from advanced_alchemy.extensions.litestar import (
    AsyncSessionConfig,
    SQLAlchemyAsyncConfig,
    SQLAlchemyPlugin,
)
from litestar import Litestar
from litestar.contrib.opentelemetry import OpenTelemetryConfig, OpenTelemetryPlugin
from litestar.di import Provide

from src.config import Settings
from src.controllers.article import ArticleController
from src.controllers.health import HealthController
from src.logging_config import build_logging_config
from src.services.notification import NotificationService


def create_app(notification_service: NotificationService | None = None) -> Litestar:
    settings = Settings.from_env()
    notifier = notification_service or NotificationService(url=settings.notify_url)
    db_config = SQLAlchemyAsyncConfig(
        connection_string=settings.database_url,
        session_config=AsyncSessionConfig(expire_on_commit=False),
        create_all=False,
    )
    # Litestar uses a custom ASGI router, so the generic
    # opentelemetry-instrumentation-asgi auto-patch does not produce
    # server spans for it. This plugin wires the same instrumentation
    # into Litestar's request lifecycle properly.
    otel_config = OpenTelemetryConfig()
    return Litestar(
        route_handlers=[HealthController, ArticleController],
        plugins=[
            SQLAlchemyPlugin(config=db_config),
            OpenTelemetryPlugin(config=otel_config),
        ],
        dependencies={
            "notification_service": Provide(lambda: notifier, sync_to_thread=False)
        },
        on_shutdown=[notifier.aclose],
        logging_config=build_logging_config(),
    )


app = create_app()
