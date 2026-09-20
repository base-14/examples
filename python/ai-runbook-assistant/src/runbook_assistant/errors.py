"""HTTP error telemetry.

An exception that escapes a route bypasses the span handling inside the
request, so the handler records it on whichever span is active when it runs.
The ASGI instrumentation only sets ERROR from status 500 up; the middleware
sets it from 400 up, because a rejected request is a failed request.
"""

import logging
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
from starlette.middleware.base import BaseHTTPMiddleware


logger = logging.getLogger(__name__)


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    span = trace.get_current_span()
    span.record_exception(exc)
    span.set_attribute("error.type", type(exc).__qualname__)
    span.set_status(Status(StatusCode.ERROR, str(exc)))

    logger.exception("Unhandled error on %s %s", request.method, request.url.path)

    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


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
