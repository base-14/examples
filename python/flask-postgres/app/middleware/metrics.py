"""HTTP metrics middleware."""

import time

from flask import Flask, g, request

from app.telemetry import get_meter


def register_metrics_middleware(app: Flask) -> None:
    """Register HTTP metrics middleware on Flask app.

    Args:
        app: Flask application instance.
    """
    meter = get_meter(__name__)

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

    @app.before_request
    def before_request() -> None:
        """Record request start time."""
        g.request_start_time = time.perf_counter()

    @app.after_request
    def after_request(response):
        """Record request metrics."""
        # Skip health check endpoints
        if request.path in ("/api/health", "/health"):
            return response

        # Calculate duration
        start_time = getattr(g, "request_start_time", None)
        if start_time:
            duration_ms = (time.perf_counter() - start_time) * 1000
        else:
            duration_ms = 0

        # Get route pattern (or path if no route matched)
        route = request.url_rule.rule if request.url_rule else request.path

        attributes = {
            "method": request.method,
            "route": route,
            "status": str(response.status_code),
        }

        http_requests_total.add(1, attributes)
        http_request_duration.record(duration_ms, attributes)

        return response
