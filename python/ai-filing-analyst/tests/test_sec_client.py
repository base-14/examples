from collections.abc import Iterator

import httpx
import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode

from filing_analyst.sec_client import (
    FAULT_BLOCKED_BACKOFF_SECONDS,
    SecBackoff,
    SecBlocked,
    SecCallCapExceeded,
    SecUnavailable,
    sec_question_scope,
)
from tests.sec_support import USER_AGENT, FakeClock, RecordingHandler, sec_client


FACTS = {"cik": 1445305, "entityName": "WORKIVA INC", "facts": {}}


def ok(_request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json=FACTS)


def statuses(*codes: int) -> RecordingHandler:
    remaining = list(codes)

    def respond(_request: httpx.Request) -> httpx.Response:
        code = remaining.pop(0) if remaining else 200
        return httpx.Response(code, json=FACTS if code == 200 else {})

    return RecordingHandler(respond)


@pytest.fixture
def spans() -> Iterator[tuple[TracerProvider, InMemorySpanExporter]]:
    memory = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(memory))
    yield provider, memory
    provider.shutdown()


def test_every_request_carries_the_user_agent_and_the_company_facts_url() -> None:
    handler = RecordingHandler(ok)
    assert sec_client(handler).company_facts(1445305) == FACTS
    (request,) = handler.requests
    assert request.headers["User-Agent"] == USER_AGENT
    assert str(request.url) == "https://data.sec.gov/api/xbrl/companyfacts/CIK0001445305.json"


def test_the_ticker_list_and_frames_urls() -> None:
    handler = RecordingHandler(ok)
    client = sec_client(handler)
    client.company_tickers()
    client.frame("us-gaap", "NetIncomeLoss", "USD", "CY2024")
    assert [str(r.url) for r in handler.requests] == [
        "https://www.sec.gov/files/company_tickers.json",
        "https://data.sec.gov/api/xbrl/frames/us-gaap/NetIncomeLoss/USD/CY2024.json",
    ]


def test_a_missing_document_reads_none() -> None:
    assert sec_client(statuses(404)).company_facts(1) is None


@pytest.mark.parametrize("code", [400, 429])
def test_another_4xx_is_unavailable_without_a_retry(code: int) -> None:
    handler = statuses(code)
    with pytest.raises(SecUnavailable):
        sec_client(handler).company_facts(1445305)
    assert len(handler.requests) == 1


def test_a_body_that_is_not_json_is_unavailable() -> None:
    handler = RecordingHandler(lambda _r: httpx.Response(200, text="<html>maintenance</html>"))
    with pytest.raises(SecUnavailable):
        sec_client(handler).company_facts(1445305)


def test_the_token_bucket_spaces_requests_below_the_rate() -> None:
    clock = FakeClock()
    client = sec_client(RecordingHandler(ok), clock)
    for _ in range(3):
        client.company_facts(1445305)
    assert clock.sleeps == pytest.approx([0.2, 0.2])


def test_a_5xx_is_retried_until_it_succeeds() -> None:
    handler = statuses(503, 502)
    clock = FakeClock()
    assert sec_client(handler, clock).company_facts(1445305) == FACTS
    assert len(handler.requests) == 3
    assert [s for s in clock.sleeps if s >= 0.5] == [0.5, 1.0]


def test_transport_errors_are_retried_three_times_then_raise() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    handler = RecordingHandler(refuse)
    with pytest.raises(SecUnavailable):
        sec_client(handler).company_facts(1445305)
    assert len(handler.requests) == 4


def test_a_403_is_not_retried_and_starts_the_back_off() -> None:
    handler = statuses(403)
    clock = FakeClock()
    client = sec_client(handler, clock)
    with pytest.raises(SecBlocked):
        client.company_facts(1445305)
    assert len(handler.requests) == 1

    with pytest.raises(SecBackoff):
        client.company_facts(1866692)
    assert len(handler.requests) == 1

    clock.now += 600
    assert client.company_facts(1866692) == FACTS
    assert len(handler.requests) == 2


def test_the_per_question_cap_refuses_without_a_request() -> None:
    handler = RecordingHandler(ok)
    client = sec_client(handler)
    with sec_question_scope(cap=2) as scope:
        client.company_facts(1)
        client.company_facts(2)
        with pytest.raises(SecCallCapExceeded):
            client.company_facts(3)
    assert scope.calls == 2
    assert len(handler.requests) == 2


def test_retries_count_as_one_call_against_the_cap() -> None:
    client = sec_client(statuses(503))
    with sec_question_scope(cap=1) as scope:
        client.company_facts(1)
    assert scope.calls == 1


def test_sec_down_fails_the_first_two_attempts() -> None:
    handler = RecordingHandler(ok)
    with sec_question_scope(cap=4, fault="sec_down"):
        assert sec_client(handler).company_facts(1) == FACTS
    assert len(handler.requests) == 1


def test_sec_unreachable_fails_every_attempt() -> None:
    handler = RecordingHandler(ok)
    with sec_question_scope(cap=4, fault="sec_unreachable"), pytest.raises(SecUnavailable):
        sec_client(handler).frame("us-gaap", "NetIncomeLoss", "USD", "CY2024")
    assert handler.requests == []


def test_sec_blocked_answers_403_with_a_short_back_off() -> None:
    handler = RecordingHandler(ok)
    clock = FakeClock()
    client = sec_client(handler, clock)
    with sec_question_scope(cap=4, fault="sec_blocked"), pytest.raises(SecBlocked):
        client.company_facts(1)
    with pytest.raises(SecBackoff):
        client.company_facts(2)
    clock.now += FAULT_BLOCKED_BACKOFF_SECONDS
    assert client.company_facts(2) == FACTS
    assert len(handler.requests) == 1


def test_faults_apply_only_inside_a_question() -> None:
    handler = RecordingHandler(ok)
    sec_client(handler).company_facts(1)
    assert len(handler.requests) == 1


def test_client_spans_carry_the_endpoint_and_attempt(
    spans: tuple[TracerProvider, InMemorySpanExporter],
) -> None:
    provider, memory = spans
    client = sec_client(RecordingHandler(ok), tracer_provider=provider)
    with sec_question_scope(cap=4, fault="sec_down"):
        client.company_facts(1445305)
    finished = memory.get_finished_spans()
    assert [(s.attributes or {})["base14.sec.attempt"] for s in finished] == [1, 2, 3]
    assert {(s.attributes or {})["base14.sec.endpoint"] for s in finished} == {"companyfacts"}
    assert [s.status.status_code for s in finished] == [
        StatusCode.ERROR,
        StatusCode.ERROR,
        StatusCode.UNSET,
    ]
