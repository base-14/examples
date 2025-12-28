"""Error handlers with OpenTelemetry trace context."""

from flask import Flask, jsonify
from opentelemetry import trace


def error_response(message: str, status_code: int) -> tuple:
    """Create error response with trace context.

    Use this function in routes instead of returning jsonify directly.

    Args:
        message: Error message.
        status_code: HTTP status code.

    Returns:
        Tuple of (response, status_code).
    """
    response = {"error": message}

    span = trace.get_current_span()
    span_context = span.get_span_context()
    if span_context.is_valid:
        response["trace_id"] = format(span_context.trace_id, "032x")

    return jsonify(response), status_code


def register_error_handlers(app: Flask) -> None:
    """Register error handlers on Flask app.

    Args:
        app: Flask application instance.
    """

    @app.errorhandler(400)
    def bad_request(error):
        return _make_error_response("Bad request", 400)

    @app.errorhandler(401)
    def unauthorized(error):
        return _make_error_response("Unauthorized", 401)

    @app.errorhandler(403)
    def forbidden(error):
        return _make_error_response("Forbidden", 403)

    @app.errorhandler(404)
    def not_found(error):
        return _make_error_response("Not found", 404)

    @app.errorhandler(409)
    def conflict(error):
        return _make_error_response("Conflict", 409)

    @app.errorhandler(500)
    def internal_error(error):
        return _make_error_response("Internal server error", 500)


def _make_error_response(message: str, status_code: int) -> tuple:
    """Create error response with trace context.

    Args:
        message: Error message.
        status_code: HTTP status code.

    Returns:
        Tuple of (response, status_code).
    """
    response = {
        "error": message,
        "status": status_code,
    }

    # Add trace ID for debugging
    span = trace.get_current_span()
    span_context = span.get_span_context()
    if span_context.is_valid:
        response["trace_id"] = format(span_context.trace_id, "032x")

    return jsonify(response), status_code
