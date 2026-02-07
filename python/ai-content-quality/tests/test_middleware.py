from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

import content_quality.middleware.metrics as metrics_mod


@patch.object(metrics_mod, "_init_metrics")
def test_middleware_records_request_count(_init: MagicMock, client: TestClient) -> None:
    mock_counter = MagicMock()
    mock_histogram = MagicMock()
    mock_updown = MagicMock()
    metrics_mod._meter = MagicMock()
    metrics_mod._request_count = mock_counter
    metrics_mod._request_duration = mock_histogram
    metrics_mod._active_requests = mock_updown

    try:
        response = client.get("/health")
        assert response.status_code == 200

        mock_counter.add.assert_called()
        call_args = mock_counter.add.call_args
        assert call_args.args[0] == 1
        attrs = call_args.args[1]
        assert attrs["http.request.method"] == "GET"
        assert attrs["http.route"] == "/health"
        assert attrs["http.response.status_code"] == 200
    finally:
        metrics_mod._meter = None
        metrics_mod._request_count = None
        metrics_mod._request_duration = None
        metrics_mod._active_requests = None


@patch.object(metrics_mod, "_init_metrics")
def test_middleware_records_request_duration(_init: MagicMock, client: TestClient) -> None:
    mock_counter = MagicMock()
    mock_histogram = MagicMock()
    mock_updown = MagicMock()
    metrics_mod._meter = MagicMock()
    metrics_mod._request_count = mock_counter
    metrics_mod._request_duration = mock_histogram
    metrics_mod._active_requests = mock_updown

    try:
        client.get("/health")

        mock_histogram.record.assert_called()
        call_args = mock_histogram.record.call_args
        duration = call_args.args[0]
        assert duration > 0
        attrs = call_args.args[1]
        assert attrs["http.request.method"] == "GET"
        assert attrs["http.route"] == "/health"
    finally:
        metrics_mod._meter = None
        metrics_mod._request_count = None
        metrics_mod._request_duration = None
        metrics_mod._active_requests = None


@patch.object(metrics_mod, "_init_metrics")
def test_middleware_tracks_active_requests(_init: MagicMock, client: TestClient) -> None:
    mock_counter = MagicMock()
    mock_histogram = MagicMock()
    mock_updown = MagicMock()
    metrics_mod._meter = MagicMock()
    metrics_mod._request_count = mock_counter
    metrics_mod._request_duration = mock_histogram
    metrics_mod._active_requests = mock_updown

    try:
        client.get("/health")

        calls = mock_updown.add.call_args_list
        assert len(calls) == 2
        assert calls[0].args[0] == 1
        assert calls[1].args[0] == -1
    finally:
        metrics_mod._meter = None
        metrics_mod._request_count = None
        metrics_mod._request_duration = None
        metrics_mod._active_requests = None


@patch.object(metrics_mod, "_init_metrics")
def test_middleware_records_500_on_error(_init: MagicMock, client: TestClient) -> None:
    mock_counter = MagicMock()
    mock_histogram = MagicMock()
    mock_updown = MagicMock()
    metrics_mod._meter = MagicMock()
    metrics_mod._request_count = mock_counter
    metrics_mod._request_duration = mock_histogram
    metrics_mod._active_requests = mock_updown

    try:
        response = client.post("/review", json={"content": "", "content_type": "blog"})
        assert response.status_code == 422

        mock_counter.add.assert_called()
        attrs = mock_counter.add.call_args.args[1]
        assert attrs["http.response.status_code"] == 422
    finally:
        metrics_mod._meter = None
        metrics_mod._request_count = None
        metrics_mod._request_duration = None
        metrics_mod._active_requests = None
