from __future__ import annotations

import logging
from typing import Any

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler

logger = logging.getLogger(__name__)


def custom_exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    response = exception_handler(exc, context)

    span = trace.get_current_span()

    if response is not None:
        status_code = response.status_code

        if span.is_recording():
            trace_id = format(span.get_span_context().trace_id, "032x")

            if status_code >= 500:
                span.set_status(Status(StatusCode.ERROR, str(exc)))
                span.record_exception(exc)
                span.set_attribute("error.type", "server_error")
                logger.error(f"Server error: {exc}", exc_info=True, extra={"trace_id": trace_id})
            elif status_code >= 400:
                error_type = _get_error_type(status_code)
                span.set_attribute("error.type", error_type)
                span.set_attribute("http.status_code", status_code)

            response.data["trace_id"] = trace_id

    elif span.is_recording():
        span.set_status(Status(StatusCode.ERROR, str(exc)))
        span.record_exception(exc)
        span.set_attribute("error.type", "unhandled_exception")
        logger.exception(f"Unhandled exception: {exc}")

        trace_id = format(span.get_span_context().trace_id, "032x")
        return Response(
            {"error": "Internal server error", "trace_id": trace_id},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    return response


def _get_error_type(status_code: int) -> str:
    error_types = {
        400: "validation",
        401: "authentication",
        403: "authorization",
        404: "not_found",
        409: "conflict",
    }
    return error_types.get(status_code, "client_error")
