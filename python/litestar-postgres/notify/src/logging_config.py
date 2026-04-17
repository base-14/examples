"""Same JSON+OTel-correlation setup as the articles service. See its
`logging_config.py` for rationale."""

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
        },
        root={"level": "INFO", "handlers": ["default"]},
    )
