from runbook_assistant.tools import get_service_status, query_metrics, search_logs


def test_query_metrics_reads_fixture():
    out = query_metrics.invoke({"service": "checkout", "metric": "memory"})
    assert "checkout" in out and "95%" in out


def test_search_logs_filters_by_pattern():
    out = search_logs.invoke({"service": "checkout", "pattern": "OOMKilled"})
    assert "OOMKilled" in out
    assert "memory cgroup" not in out


def test_service_status_reads_fixture():
    out = get_service_status.invoke({"service": "checkout"})
    assert "checkout" in out and "2/3" in out


def test_unknown_service_is_handled():
    assert "unknown" in get_service_status.invoke({"service": "nope"}).lower()
