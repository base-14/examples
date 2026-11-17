"""Tests for error recording on FastAPI's server spans."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.trace import SpanKind, StatusCode

from sales_intelligence.errors import unhandled_exception_handler
from sales_intelligence.middleware import SpanStatusMiddleware
from sales_intelligence.telemetry import FASTAPI_TELEMETRY


@pytest.fixture
def client() -> TestClient:
    """A minimal app wired with the same telemetry, handler and middleware as the real one."""
    app = FastAPI(telemetry=FASTAPI_TELEMETRY)
    app.add_middleware(SpanStatusMiddleware)
    app.add_exception_handler(Exception, unhandled_exception_handler)

    @app.get("/ok")
    async def ok() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/boom")
    async def boom() -> dict[str, str]:
        raise ValueError("something broke")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "healthy"}

    return TestClient(app, raise_server_exceptions=False)


def server_spans(span_exporter) -> list[ReadableSpan]:
    return [s for s in span_exporter.get_finished_spans() if s.kind is SpanKind.SERVER]


class TestServerSpans:
    def test_names_the_span_after_the_route(self, client, span_exporter):
        client.get("/ok")

        (span,) = server_spans(span_exporter)
        assert span.name == "GET /ok"
        assert span.attributes["http.route"] == "/ok"
        assert span.attributes["http.response.status_code"] == 200

    def test_leaves_the_health_check_untraced(self, client, span_exporter):
        client.get("/health")

        assert server_spans(span_exporter) == []


class TestSpanStatusMiddleware:
    def test_success_leaves_span_unset(self, client, span_exporter):
        response = client.get("/ok")

        assert response.status_code == 200
        (span,) = server_spans(span_exporter)
        assert span.status.status_code is StatusCode.UNSET

    def test_client_error_marks_span_error(self, client, span_exporter):
        response = client.get("/missing")

        assert response.status_code == 404
        (span,) = server_spans(span_exporter)
        assert span.status.status_code is StatusCode.ERROR
        assert span.attributes["error.type"] == "404"


class TestUnhandledExceptionHandler:
    def test_records_the_exception_on_the_server_span(self, client, span_exporter):
        response = client.get("/boom")

        assert response.status_code == 500
        assert response.json() == {"detail": "Internal server error"}

        (span,) = server_spans(span_exporter)
        assert span.status.status_code is StatusCode.ERROR
        assert span.attributes["error.type"] == "ValueError"
        assert [e.name for e in span.events] == ["exception"]
