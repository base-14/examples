from __future__ import annotations

import time
from collections.abc import Callable
from typing import TYPE_CHECKING

from opentelemetry import trace

from .telemetry import get_meter

if TYPE_CHECKING:
    from django.http import HttpRequest, HttpResponse

meter = get_meter("apps.core.middleware")

http_requests_total = meter.create_counter(
    name="http_requests_total",
    description="Total HTTP requests",
    unit="1",
)

http_request_duration = meter.create_histogram(
    name="http_request_duration_ms",
    description="HTTP request duration in milliseconds",
    unit="ms",
)


class MetricsMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        start_time = time.perf_counter()

        response = self.get_response(request)

        duration_ms = (time.perf_counter() - start_time) * 1000

        path = request.path
        if path.startswith("/api/articles/") and len(path.split("/")) > 3:
            path = "/api/articles/{slug}"

        attributes = {
            "http.method": request.method,
            "http.route": path,
            "http.status_code": response.status_code,
        }

        http_requests_total.add(1, attributes)
        http_request_duration.record(duration_ms, attributes)

        span = trace.get_current_span()
        if span.is_recording():
            span.set_attribute("http.route", path)

        return response
