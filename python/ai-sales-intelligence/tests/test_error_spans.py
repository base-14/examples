"""Tests for error recording on HTTP spans."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from opentelemetry import trace
from opentelemetry.trace import SpanKind, StatusCode

from sales_intelligence.errors import unhandled_exception_handler
from sales_intelligence.middleware import SpanStatusMiddleware


tracer = trace.get_tracer(__name__)


@pytest.fixture
def client() -> TestClient:
    """A minimal app wired with the same handler and middleware as the real one."""
    app = FastAPI()
    app.add_middleware(SpanStatusMiddleware)
    app.add_exception_handler(Exception, unhandled_exception_handler)

    @app.get("/ok")
    async def ok() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/boom")
    async def boom() -> dict[str, str]:
        raise ValueError("something broke")

    return TestClient(app, raise_server_exceptions=False)


def request_in_span(client: TestClient, path: str):
    """Issue a request inside a server span and return the response."""
    with tracer.start_as_current_span("GET " + path, kind=SpanKind.SERVER):
        response = client.get(path)
    return response


class TestSpanStatusMiddleware:
    def test_success_leaves_span_unset(self, client, span_exporter):
        response = request_in_span(client, "/ok")

        assert response.status_code == 200
        span = span_exporter.get_finished_spans()[0]
        assert span.status.status_code is StatusCode.UNSET

    def test_client_error_marks_span_error(self, client, span_exporter):
        response = request_in_span(client, "/missing")

        assert response.status_code == 404
        span = span_exporter.get_finished_spans()[0]
        assert span.status.status_code is StatusCode.ERROR
        assert span.attributes["error.type"] == "404"


class TestUnhandledExceptionHandler:
    def test_records_the_exception_on_the_active_span(self, client, span_exporter):
        response = request_in_span(client, "/boom")

        assert response.status_code == 500
        assert response.json() == {"detail": "Internal server error"}

        span = span_exporter.get_finished_spans()[0]
        assert span.status.status_code is StatusCode.ERROR
        assert span.attributes["error.type"] == "ValueError"
        assert [e.name for e in span.events] == ["exception"]
