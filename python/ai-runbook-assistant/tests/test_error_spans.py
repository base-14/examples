import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from opentelemetry.trace import SpanKind, StatusCode

from runbook_assistant.errors import SpanStatusMiddleware, unhandled_exception_handler
from runbook_assistant.telemetry.setup import FASTAPI_TELEMETRY


@pytest.fixture
def client() -> TestClient:
    app = FastAPI(telemetry=FASTAPI_TELEMETRY)
    app.add_middleware(SpanStatusMiddleware)
    app.add_exception_handler(Exception, unhandled_exception_handler)

    @app.get("/ok")
    async def ok() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/missing")
    async def missing() -> dict[str, str]:
        raise HTTPException(status_code=404, detail="nope")

    @app.get("/boom")
    async def boom() -> dict[str, str]:
        raise ValueError("boom")

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return TestClient(app, raise_server_exceptions=False)


def _server_spans(span_exporter):
    return [s for s in span_exporter.get_finished_spans() if s.kind is SpanKind.SERVER]


def _request(client: TestClient, path: str, span_exporter):
    response = client.get(path)
    (span,) = _server_spans(span_exporter)
    return response, span


def test_the_server_span_is_named_after_the_route(client, span_exporter):
    _, span = _request(client, "/ok", span_exporter)
    assert span.name == "GET /ok"
    assert span.attributes["http.route"] == "/ok"


def test_health_checks_are_not_traced(client, span_exporter):
    client.get("/healthz")
    assert _server_spans(span_exporter) == []


def test_success_leaves_the_server_span_unset(client, span_exporter):
    response, span = _request(client, "/ok", span_exporter)
    assert response.status_code == 200
    assert span.status.status_code is not StatusCode.ERROR


def test_client_error_marks_the_server_span(client, span_exporter):
    response, span = _request(client, "/missing", span_exporter)
    assert response.status_code == 404
    assert span.status.status_code is StatusCode.ERROR
    assert span.attributes["error.type"] == "404"


def test_unhandled_exception_is_recorded_and_returns_500(client, span_exporter):
    response, span = _request(client, "/boom", span_exporter)
    assert response.status_code == 500
    assert span.status.status_code is StatusCode.ERROR
    assert span.attributes["error.type"] == "ValueError"
    assert [e.name for e in span.events] == ["exception"]
