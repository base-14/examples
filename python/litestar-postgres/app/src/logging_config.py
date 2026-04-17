"""Structured logging setup, wired through Litestar's LoggingConfig.

`opentelemetry-instrumentation-logging` (auto-loaded by `opentelemetry-instrument`
when `OTEL_PYTHON_LOG_CORRELATION=true`) injects `otelTraceID`, `otelSpanID`,
`otelTraceSampled`, `otelServiceName` onto every LogRecord. We surface those
fields in the JSON output so trace-log correlation works end-to-end in Scout.

Returning a `LoggingConfig` (rather than mutating `logging` directly) is what
prevents Litestar from clobbering our handlers during `Litestar(...)` init.
"""

from litestar.logging.config import LoggingConfig

_FORMAT = (
    "%(asctime)s %(levelname)s %(name)s %(message)s "
    "%(otelTraceID)s %(otelSpanID)s %(otelTraceSampled)s %(otelServiceName)s"
)


def build_logging_config() -> LoggingConfig:
    return LoggingConfig(
        formatters={
            "json": {
                "()": "pythonjsonlogger.json.JsonFormatter",
                "format": _FORMAT,
            }
        },
        handlers={
            "default": {
                "class": "logging.StreamHandler",
                "formatter": "json",
                "stream": "ext://sys.stdout",
            }
        },
        loggers={
            "uvicorn.access": {
                "level": "INFO",
                "handlers": ["default"],
                "propagate": False,
            },
            "uvicorn.error": {
                "level": "INFO",
                "handlers": ["default"],
                "propagate": False,
            },
            "sqlalchemy.engine": {
                "level": "WARNING",
                "handlers": ["default"],
                "propagate": False,
            },
        },
        root={"level": "INFO", "handlers": ["default"]},
    )
