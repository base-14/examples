"""Marks the HTTP server span as failed for error responses.

The ASGI instrumentation only sets ERROR from status 500 up. Client errors are
failures of the request too, so this middleware sets ERROR from 400 up. The
instrumentation's later UNSET status for 4xx is ignored by the SDK, so the
status set here survives.
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
