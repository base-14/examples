import time
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import Request, Response
from opentelemetry import metrics
from starlette.middleware.base import BaseHTTPMiddleware


_meter: metrics.Meter | None = None
_request_count: metrics.Counter | None = None
_request_duration: metrics.Histogram | None = None
_active_requests: metrics.UpDownCounter | None = None


def _init_metrics() -> None:
    global _meter, _request_count, _request_duration, _active_requests
    if _meter is None:
        _meter = metrics.get_meter("http.server")
        _request_count = _meter.create_counter(
            name="http.server.request.count",
            description="Total HTTP requests",
            unit="{request}",
        )
        _request_duration = _meter.create_histogram(
            name="http.server.request.duration",
            description="HTTP request duration",
            unit="s",
        )
        _active_requests = _meter.create_up_down_counter(
            name="http.server.active_requests",
            description="Number of active HTTP requests",
            unit="{request}",
        )


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        _init_metrics()
        attributes: dict[str, Any] = {
            "http.request.method": request.method,
            "http.route": request.url.path,
        }
        assert _active_requests is not None
        assert _request_count is not None
        assert _request_duration is not None

        _active_requests.add(1, attributes)
        start_time = time.perf_counter()

        try:
            response = await call_next(request)
            attributes["http.response.status_code"] = response.status_code
            return response
        except Exception:
            attributes["http.response.status_code"] = 500
            raise
        finally:
            duration = time.perf_counter() - start_time
            _request_count.add(1, attributes)
            _request_duration.record(duration, attributes)
            _active_requests.add(
                -1, {"http.request.method": request.method, "http.route": request.url.path}
            )
