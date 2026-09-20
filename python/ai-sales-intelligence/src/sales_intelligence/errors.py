"""Error handling for exceptions that reach the framework.

An exception that escapes a route may bypass the span wrappers inside the
request, so the handler records it on whichever span is active when it runs.
"""

import logging

from fastapi import Request
from fastapi.responses import JSONResponse
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode


logger = logging.getLogger(__name__)


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Record the error on the active span and return a 500 JSON body."""
    span = trace.get_current_span()
    span.record_exception(exc)
    span.set_attribute("error.type", type(exc).__qualname__)
    span.set_status(Status(StatusCode.ERROR, str(exc)))

    logger.exception("Unhandled error on %s %s", request.method, request.url.path)

    return JSONResponse(status_code=500, content={"detail": "Internal server error"})
