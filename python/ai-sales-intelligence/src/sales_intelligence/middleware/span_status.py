"""Marks the HTTP server span as failed for error responses.

FastAPI's telemetry sets ERROR only from status 500 up. Client errors are
failures of the request too, so this middleware sets ERROR from 400 up on the
server span, which is the current span while the middleware runs.
"""

from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
from starlette.middleware.base import BaseHTTPMiddleware


class SpanStatusMiddleware(BaseHTTPMiddleware):
    """Sets ERROR on the server span for responses with status 400 and above."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)

        if response.status_code >= 400:
            span = trace.get_current_span()
            span.set_attribute("error.type", str(response.status_code))
            span.set_status(Status(StatusCode.ERROR, f"HTTP {response.status_code}"))

        return response
