import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from opentelemetry import trace
from opentelemetry.trace import StatusCode

from runbook_assistant.errors import SpanStatusMiddleware, unhandled_exception_handler


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
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

    return TestClient(app, raise_server_exceptions=False)


def _request(client: TestClient, path: str, span_exporter):
    tracer = trace.get_tracer("test")
    with tracer.start_as_current_span("GET " + path):
        response = client.get(path)
    return response, next(s for s in span_exporter.get_finished_spans() if s.name.endswith(path))


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
