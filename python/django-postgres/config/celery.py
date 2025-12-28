from __future__ import annotations

import logging
import os

from celery import Celery
from celery.signals import worker_process_init, worker_ready

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("config")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks(["apps.jobs"])

logger = logging.getLogger(__name__)


@worker_process_init.connect
def init_worker_telemetry(**kwargs: object) -> None:
    """Initialize telemetry in each forked worker process."""
    from apps.core.telemetry import get_otel_log_handler, setup_telemetry

    setup_telemetry()

    handler = get_otel_log_handler()
    if handler:
        root_logger = logging.getLogger()
        if handler not in root_logger.handlers:
            root_logger.addHandler(handler)


@worker_ready.connect
def on_worker_ready(**kwargs: object) -> None:
    logger.info("Celery worker started and ready to process tasks")
