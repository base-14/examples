from __future__ import annotations

import logging
import time
from typing import Any

from celery import Task, shared_task
from opentelemetry.trace import SpanKind, Status, StatusCode

from apps.core.telemetry import get_meter, get_tracer

logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)
meter = get_meter(__name__)

jobs_completed = meter.create_counter(
    name="jobs.completed",
    description="Completed jobs",
    unit="1",
)

jobs_failed = meter.create_counter(
    name="jobs.failed",
    description="Failed jobs",
    unit="1",
)

job_duration = meter.create_histogram(
    name="jobs.duration_ms",
    description="Job duration in milliseconds",
    unit="ms",
)


@shared_task(bind=True, max_retries=3)
def send_article_notification(
    self: Task[..., dict[str, Any]], article_id: int, event_type: str
) -> dict[str, Any]:
    start_time = time.perf_counter()

    with tracer.start_as_current_span(
        "job.send_article_notification",
        kind=SpanKind.CONSUMER,
    ) as span:
        span.set_attribute("job.name", "send_article_notification")
        span.set_attribute("job.id", self.request.id or "unknown")
        span.set_attribute("job.attempt", self.request.retries + 1)
        span.set_attribute("article.id", article_id)
        span.set_attribute("event.type", event_type)

        try:
            from apps.articles.models import Article

            article = Article.objects.select_related("author").get(id=article_id)

            logger.info(
                f"Sending {event_type} notification for article '{article.title}' "
                f"by {article.author.email}"
            )

            time.sleep(0.1)

            span.set_attribute("article.slug", article.slug)
            span.set_attribute("article.author_id", article.author_id)
            span.set_status(Status(StatusCode.OK))

            duration_ms = (time.perf_counter() - start_time) * 1000
            jobs_completed.add(
                1, {"job_name": "send_article_notification", "event_type": event_type}
            )
            job_duration.record(duration_ms, {"job_name": "send_article_notification"})

            logger.info(f"Notification sent successfully for article {article_id}")
            return {"status": "success", "article_id": article_id}

        except Exception as exc:
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            span.record_exception(exc)

            duration_ms = (time.perf_counter() - start_time) * 1000
            jobs_failed.add(
                1, {"job_name": "send_article_notification", "error": type(exc).__name__}
            )
            job_duration.record(duration_ms, {"job_name": "send_article_notification"})

            logger.exception(f"Failed to send notification for article {article_id}")
            raise self.retry(exc=exc, countdown=2**self.request.retries)
