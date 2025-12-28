"""Celery application configuration with OpenTelemetry."""

import logging
import os

from celery import Celery
from celery.signals import worker_process_init


# Create Celery app
celery = Celery(
    "flask-postgres",
    broker=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
    backend=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
)

# Celery configuration
celery.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=300,  # 5 minutes
    task_soft_time_limit=240,  # 4 minutes
    worker_hijack_root_logger=False,  # Allow OTel to manage logging
)

# Auto-discover tasks
celery.autodiscover_tasks(["app.jobs"])


@worker_process_init.connect
def init_worker_telemetry(**kwargs) -> None:
    """Initialize telemetry in each forked worker process.

    Workers fork from the main process, so telemetry must be
    initialized separately in each worker.
    """
    if os.getenv("OTEL_SDK_DISABLED"):
        return

    from app.telemetry import get_otel_log_handler, setup_telemetry

    setup_telemetry()

    # Attach log handler directly to app.jobs loggers
    handler = get_otel_log_handler()
    if handler:
        # Attach to app.jobs.tasks logger directly
        tasks_logger = logging.getLogger("app.jobs.tasks")
        tasks_logger.setLevel(logging.DEBUG)
        if handler not in tasks_logger.handlers:
            tasks_logger.addHandler(handler)

        # Also attach to app.jobs for this init message
        jobs_logger = logging.getLogger("app.jobs")
        jobs_logger.setLevel(logging.DEBUG)
        if handler not in jobs_logger.handlers:
            jobs_logger.addHandler(handler)

    logging.getLogger("app.jobs").info("Worker telemetry initialized")
