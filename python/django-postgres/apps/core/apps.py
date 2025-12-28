from __future__ import annotations

import logging

from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.core"

    def ready(self) -> None:
        from apps.core.telemetry import get_otel_log_handler

        handler = get_otel_log_handler()
        if handler:
            root_logger = logging.getLogger()
            if handler not in root_logger.handlers:
                root_logger.addHandler(handler)
