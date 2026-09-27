"""The example's own metrics, beside the `strands.*` set Strands emits.

Instruments are made on the global meter at import. Until the API sets the meter provider
they are proxies, and they record into it once it is set.
"""

from enum import StrEnum

from opentelemetry import metrics


OUTCOME_ATTRIBUTE = "base14.filing.outcome"


class Outcome(StrEnum):
    ANSWERED = "answered"
    NOT_AVAILABLE = "not_available"
    UNGROUNDED = "ungrounded"
    BUDGET = "budget"
    TIMEOUT = "timeout"
    ERROR = "error"
    REJECTED = "rejected"


_meter = metrics.get_meter("filing_analyst")

QUESTIONS = _meter.create_counter(
    "base14.filing.questions", unit="{question}", description="Questions answered, by outcome."
)
QUESTION_DURATION = _meter.create_histogram(
    "base14.filing.question.duration",
    unit="s",
    description="Time from a question arriving to its response, by outcome.",
)
SEC_REQUESTS = _meter.create_counter(
    "base14.filing.sec.requests",
    unit="{request}",
    description="HTTP requests to the SEC, by endpoint and response status.",
)
FACTS_LOADED = _meter.create_counter(
    "base14.filing.facts.loaded", unit="{fact}", description="Fact rows written to Postgres."
)
RANKINGS = _meter.create_counter(
    "base14.filing.rankings",
    unit="{ranking}",
    description="Calls to the ranking agent, by outcome.",
)
