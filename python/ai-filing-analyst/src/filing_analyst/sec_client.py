"""The one client for the SEC's XBRL APIs.

Every request carries the contact User-Agent the SEC requires, waits its turn in a token bucket
below the SEC's ten requests a second, and retries transport errors and 5xx responses. A 403 is
the SEC's throttle: the client raises at once and every call inside the back-off window fails
fast without a request. Inside a question, each call counts against the question's cap, and the
question's fault switch, if any, applies.
"""

import logging
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import httpx
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor, RequestInfo
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.trace import Span

from filing_analyst.app_metrics import SEC_REQUESTS


SEC_WWW = "https://www.sec.gov"
SEC_DATA = "https://data.sec.gov"
ENDPOINT_ATTRIBUTE = "base14.sec.endpoint"
ATTEMPT_ATTRIBUTE = "base14.sec.attempt"
RETRY_DELAYS_SECONDS = (0.5, 1.0, 2.0)
FAULT_BLOCKED_BACKOFF_SECONDS = 20
SEC_DOWN_FAILED_ATTEMPTS = 2
REQUEST_TIMEOUT_SECONDS = 30.0

logger = logging.getLogger(__name__)


class SecEndpoint(StrEnum):
    TICKERS = "tickers"
    COMPANYFACTS = "companyfacts"
    FRAMES = "frames"


class SecFault(StrEnum):
    SEC_DOWN = "sec_down"
    SEC_UNREACHABLE = "sec_unreachable"
    SEC_BLOCKED = "sec_blocked"


class SecError(Exception):
    reason = "sec_unavailable"


class SecUnavailable(SecError):
    """Retries ran out on transport errors or 5xx responses."""


class SecBlocked(SecError):
    """The SEC answered 403; the back-off window has started."""


class SecBackoff(SecError):
    """A call inside the back-off window, refused without a request."""

    reason = "sec_backoff"


class SecCallCapExceeded(SecError):
    """The question has used its SEC calls."""


@dataclass
class SecQuestionScope:
    cap: int
    fault: str | None = None
    calls: int = 0


_question: ContextVar[SecQuestionScope | None] = ContextVar("sec_question", default=None)


@contextmanager
def sec_question_scope(cap: int, fault: str | None = None) -> Iterator[SecQuestionScope]:
    """Count SEC calls against `cap` and apply `fault` for the code run inside, including
    tools Strands runs in worker threads, which copy the context."""
    scope = SecQuestionScope(cap=cap, fault=fault)
    token = _question.set(scope)
    try:
        yield scope
    finally:
        _question.reset(token)


def _current_fault() -> str | None:
    scope = _question.get()
    return scope.fault if scope else None


class FaultInjectingTransport(httpx.BaseTransport):
    """Fails requests the way the question's SEC fault asks, below the httpx instrumentation,
    so each failed attempt is a client span with error status."""

    def __init__(self, inner: httpx.BaseTransport) -> None:
        self._inner = inner

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        fault = _current_fault()
        attempt = int(request.extensions.get(ATTEMPT_ATTRIBUTE, 1))
        if fault == SecFault.SEC_UNREACHABLE or (
            fault == SecFault.SEC_DOWN and attempt <= SEC_DOWN_FAILED_ATTEMPTS
        ):
            raise httpx.ConnectError(f"injected {fault}", request=request)
        if fault == SecFault.SEC_BLOCKED:
            return httpx.Response(403, request=request)
        return self._inner.handle_request(request)

    def close(self) -> None:
        self._inner.close()


def _tag_span(span: Span, request: RequestInfo) -> None:
    extensions = request.extensions or {}
    for key in (ENDPOINT_ATTRIBUTE, ATTEMPT_ATTRIBUTE):
        if key in extensions:
            span.set_attribute(key, extensions[key])


class SecClient:
    def __init__(
        self,
        user_agent: str,
        requests_per_second: float,
        backoff_seconds: int,
        *,
        transport: httpx.BaseTransport | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        tracer_provider: TracerProvider | None = None,
    ) -> None:
        self._interval = 1.0 / requests_per_second
        self._backoff_seconds = backoff_seconds
        self._clock = clock
        self._sleep = sleep
        self._lock = threading.Lock()
        self._next_slot = 0.0
        self._blocked_until = 0.0
        self._client = httpx.Client(
            headers={"User-Agent": user_agent, "Accept-Encoding": "gzip, deflate"},
            transport=FaultInjectingTransport(transport or httpx.HTTPTransport()),
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        HTTPXClientInstrumentor.instrument_client(
            self._client, tracer_provider=tracer_provider, request_hook=_tag_span
        )

    def company_tickers(self) -> Any:
        return self._get_json(SecEndpoint.TICKERS, f"{SEC_WWW}/files/company_tickers.json")

    def company_facts(self, cik: int) -> Any:
        return self._get_json(
            SecEndpoint.COMPANYFACTS, f"{SEC_DATA}/api/xbrl/companyfacts/CIK{cik:010d}.json"
        )

    def frame(self, taxonomy: str, concept: str, unit: str, period: str) -> Any:
        return self._get_json(
            SecEndpoint.FRAMES,
            f"{SEC_DATA}/api/xbrl/frames/{taxonomy}/{concept}/{unit}/{period}.json",
        )

    def close(self) -> None:
        self._client.close()

    def _wait_for_slot(self) -> None:
        with self._lock:
            now = self._clock()
            slot = max(now, self._next_slot)
            self._next_slot = slot + self._interval
        if slot > now:
            self._sleep(slot - now)

    def _start_backoff(self) -> None:
        seconds = (
            FAULT_BLOCKED_BACKOFF_SECONDS
            if _current_fault() == SecFault.SEC_BLOCKED
            else self._backoff_seconds
        )
        with self._lock:
            self._blocked_until = self._clock() + seconds

    def _count_call(self, endpoint: SecEndpoint) -> None:
        if self._clock() < self._blocked_until:
            raise SecBackoff(f"SEC back-off in force; {endpoint} call refused")
        scope = _question.get()
        if scope is None:
            return
        if scope.calls >= scope.cap:
            raise SecCallCapExceeded(f"question used its {scope.cap} SEC calls")
        scope.calls += 1

    def _get_json(self, endpoint: SecEndpoint, url: str) -> Any:
        """The decoded body, or `None` when the SEC has no such document."""
        self._count_call(endpoint)
        attempts = len(RETRY_DELAYS_SECONDS) + 1
        for attempt in range(1, attempts + 1):
            self._wait_for_slot()
            try:
                response = self._client.get(
                    url, extensions={ENDPOINT_ATTRIBUTE: str(endpoint), ATTEMPT_ATTRIBUTE: attempt}
                )
            except httpx.TransportError as error:
                problem = type(error).__name__
                SEC_REQUESTS.add(1, {ENDPOINT_ATTRIBUTE: str(endpoint), "error.type": problem})
            else:
                SEC_REQUESTS.add(
                    1,
                    {
                        ENDPOINT_ATTRIBUTE: str(endpoint),
                        "http.response.status_code": response.status_code,
                    },
                )
                if response.status_code == httpx.codes.FORBIDDEN:
                    self._start_backoff()
                    logger.error("SEC answered 403 on %s; back-off started", endpoint)
                    raise SecBlocked(f"SEC answered 403 on {endpoint}")
                if response.status_code == httpx.codes.NOT_FOUND:
                    return None
                if response.status_code < httpx.codes.INTERNAL_SERVER_ERROR:
                    return _decoded(endpoint, response)
                problem = str(response.status_code)
            if attempt < attempts:
                logger.warning(
                    "SEC %s attempt %d failed with %s; retrying", endpoint, attempt, problem
                )
                self._sleep(RETRY_DELAYS_SECONDS[attempt - 1])
        logger.error("SEC %s failed after %d attempts: %s", endpoint, attempts, problem)
        raise SecUnavailable(f"SEC {endpoint} failed after {attempts} attempts: {problem}")


def _decoded(endpoint: SecEndpoint, response: httpx.Response) -> Any:
    if response.is_error:
        logger.error("SEC answered %d on %s", response.status_code, endpoint)
        raise SecUnavailable(f"SEC answered {response.status_code} on {endpoint}")
    try:
        return response.json()
    except ValueError as error:
        logger.error("SEC %s body is not JSON", endpoint)
        raise SecUnavailable(f"SEC {endpoint} body is not JSON") from error
