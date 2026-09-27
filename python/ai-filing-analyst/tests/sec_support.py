from collections.abc import Callable

import httpx

from filing_analyst.sec_client import SecClient


USER_AGENT = "Example Co ops@example.com"


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


class RecordingHandler:
    def __init__(self, respond: Callable[[httpx.Request], httpx.Response]) -> None:
        self.requests: list[httpx.Request] = []
        self._respond = respond

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self._respond(request)


def sec_client(
    handler: RecordingHandler,
    clock: FakeClock | None = None,
    **kwargs: object,
) -> SecClient:
    clock = clock or FakeClock()
    options: dict[str, object] = {
        "user_agent": USER_AGENT,
        "requests_per_second": 5.0,
        "backoff_seconds": 600,
        "transport": httpx.MockTransport(handler),
        "clock": clock,
        "sleep": clock.sleep,
    }
    options.update(kwargs)
    return SecClient(**options)  # type: ignore[arg-type]
