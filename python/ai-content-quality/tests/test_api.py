from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient
from opentelemetry.trace import StatusCode


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "ai-content-quality"


def test_unknown_route_returns_404(client: TestClient) -> None:
    response = client.get("/nonexistent")
    assert response.status_code == 404


def test_review_returns_review_result(client: TestClient) -> None:
    response = client.post("/review", json={"content": "Test content for review."})
    assert response.status_code == 200
    data = response.json()
    assert "issues" in data
    assert "summary" in data
    assert "overall_quality" in data
    assert data["overall_quality"] in ("poor", "fair", "good", "excellent")


def test_review_includes_issues(client: TestClient) -> None:
    response = client.post("/review", json={"content": "Test content."})
    data = response.json()
    assert len(data["issues"]) == 1
    issue = data["issues"][0]
    assert issue["type"] == "grammar"
    assert issue["severity"] == "low"


def test_improve_returns_improve_result(client: TestClient) -> None:
    response = client.post("/improve", json={"content": "Test content for improvement."})
    assert response.status_code == 200
    data = response.json()
    assert "suggestions" in data
    assert "summary" in data
    assert len(data["suggestions"]) == 1
    suggestion = data["suggestions"][0]
    assert "original" in suggestion
    assert "improved" in suggestion
    assert "reason" in suggestion


def test_score_returns_score_result(client: TestClient) -> None:
    response = client.post("/score", json={"content": "Test content for scoring."})
    assert response.status_code == 200
    data = response.json()
    assert "score" in data
    assert "breakdown" in data
    assert "summary" in data
    assert 0 <= data["score"] <= 100
    breakdown = data["breakdown"]
    for key in ("clarity", "accuracy", "engagement", "originality"):
        assert 0 <= breakdown[key] <= 100


def test_content_type_passed_to_analyzer(client: TestClient, mock_analyzer: AsyncMock) -> None:
    client.post("/review", json={"content": "Marketing copy.", "content_type": "marketing"})
    mock_analyzer.review.assert_called_once_with("Marketing copy.", "marketing")


def test_empty_content_returns_422(client: TestClient) -> None:
    response = client.post("/review", json={"content": ""})
    assert response.status_code == 422


def test_exceeds_max_length_returns_422(client: TestClient) -> None:
    response = client.post("/review", json={"content": "x" * 10_001})
    assert response.status_code == 422


def test_invalid_content_type_returns_422(client: TestClient) -> None:
    response = client.post("/review", json={"content": "Hello", "content_type": "invalid"})
    assert response.status_code == 422


def test_missing_content_returns_422(client: TestClient) -> None:
    response = client.post("/review", json={})
    assert response.status_code == 422


def test_timeout_returns_504(client: TestClient, mock_analyzer: AsyncMock) -> None:
    mock_analyzer.review.side_effect = TimeoutError()
    response = client.post("/review", json={"content": "Slow content."})
    assert response.status_code == 504
    assert response.json()["detail"] == "Analysis timed out"


def test_llm_error_returns_502(client: TestClient, mock_analyzer: AsyncMock) -> None:
    mock_analyzer.review.side_effect = RuntimeError("LLM connection failed")
    response = client.post("/review", json={"content": "Some content."})
    assert response.status_code == 502
    assert response.json()["detail"] == "Analysis failed"


def test_timeout_records_error_on_span(client: TestClient, mock_analyzer: AsyncMock) -> None:
    mock_analyzer.review.side_effect = TimeoutError()
    mock_span = MagicMock()
    mock_span.is_recording.return_value = True

    with patch("content_quality.main.trace") as mock_trace:
        mock_trace.get_current_span.return_value = mock_span
        response = client.post("/review", json={"content": "Slow content."})

    assert response.status_code == 504
    mock_span.record_exception.assert_called_once()
    mock_span.set_attribute.assert_any_call("error.type", "TimeoutError")
    mock_span.set_status.assert_called_once()
    assert mock_span.set_status.call_args.args[0] == StatusCode.ERROR


def test_llm_error_records_error_on_span(client: TestClient, mock_analyzer: AsyncMock) -> None:
    mock_analyzer.score.side_effect = RuntimeError("LLM crashed")
    mock_span = MagicMock()
    mock_span.is_recording.return_value = True

    with patch("content_quality.main.trace") as mock_trace:
        mock_trace.get_current_span.return_value = mock_span
        response = client.post("/score", json={"content": "Some content."})

    assert response.status_code == 502
    mock_span.record_exception.assert_called_once()
    mock_span.set_attribute.assert_any_call("error.type", "RuntimeError")
    mock_span.set_status.assert_called_once()
    assert mock_span.set_status.call_args.args[0] == StatusCode.ERROR


def test_timeout_on_improve_returns_504(client: TestClient, mock_analyzer: AsyncMock) -> None:
    mock_analyzer.improve.side_effect = TimeoutError()
    response = client.post("/improve", json={"content": "Slow content."})
    assert response.status_code == 504
    assert response.json()["detail"] == "Analysis timed out"


def test_llm_error_on_improve_returns_502(client: TestClient, mock_analyzer: AsyncMock) -> None:
    mock_analyzer.improve.side_effect = RuntimeError("LLM failed")
    response = client.post("/improve", json={"content": "Some content."})
    assert response.status_code == 502
    assert response.json()["detail"] == "Analysis failed"


def test_timeout_on_score_returns_504(client: TestClient, mock_analyzer: AsyncMock) -> None:
    mock_analyzer.score.side_effect = TimeoutError()
    response = client.post("/score", json={"content": "Slow content."})
    assert response.status_code == 504
    assert response.json()["detail"] == "Analysis timed out"


def test_error_on_span_skipped_when_not_recording(
    client: TestClient, mock_analyzer: AsyncMock
) -> None:
    mock_analyzer.review.side_effect = TimeoutError()
    mock_span = MagicMock()
    mock_span.is_recording.return_value = False

    with patch("content_quality.main.trace") as mock_trace:
        mock_trace.get_current_span.return_value = mock_span
        response = client.post("/review", json={"content": "Content."})

    assert response.status_code == 504
    mock_span.record_exception.assert_not_called()
    mock_span.set_attribute.assert_not_called()
    mock_span.set_status.assert_not_called()


def test_improve_records_error_on_span(client: TestClient, mock_analyzer: AsyncMock) -> None:
    mock_analyzer.improve.side_effect = RuntimeError("LLM crashed")
    mock_span = MagicMock()
    mock_span.is_recording.return_value = True

    with patch("content_quality.main.trace") as mock_trace:
        mock_trace.get_current_span.return_value = mock_span
        response = client.post("/improve", json={"content": "Some content."})

    assert response.status_code == 502
    mock_span.record_exception.assert_called_once()
    mock_span.set_attribute.assert_any_call("error.type", "RuntimeError")
    mock_span.set_status.assert_called_once()
    assert mock_span.set_status.call_args.args[0] == StatusCode.ERROR


def test_validation_error_records_error_on_span(client: TestClient) -> None:
    mock_span = MagicMock()
    mock_span.is_recording.return_value = True

    with patch("content_quality.main.trace") as mock_trace:
        mock_trace.get_current_span.return_value = mock_span
        response = client.post("/review", json={"content": ""})

    assert response.status_code == 422
    mock_span.record_exception.assert_called_once()
    mock_span.set_attribute.assert_any_call("error.type", "RequestValidationError")
    mock_span.set_status.assert_called_once()
