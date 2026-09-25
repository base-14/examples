"""The application metrics.

Workflow code records through the process-wide `ReplaySafeMeterProvider`, so replay records
nothing. Each function fetches its instrument on every call, so it binds to whichever
provider the process installed.
"""

from datetime import timedelta
from typing import Literal

from opentelemetry import metrics

from kyc_onboarding.attributes import (
    DOCUMENT_TYPE_ATTRIBUTE,
    ESCALATION_REASON_ATTRIBUTE,
    OUTCOME_ATTRIBUTE,
    REVIEW_DECISION_ATTRIBUTE,
    SANCTIONS_RESULT_ATTRIBUTE,
)


CASES = "base14.kyc.cases"
CASE_DURATION = "base14.kyc.case.duration"
RESUBMISSIONS = "base14.kyc.resubmissions"
REVIEW_WAIT = "base14.kyc.review.wait"
SANCTIONS_CHECKS = "base14.kyc.sanctions.checks"

SanctionsCheckResult = Literal["clear", "near_match", "match", "error"]
ReviewWaitDecision = Literal["approve", "reject", "expired"]

WAIT_BUCKETS_SECONDS = (
    1.0,
    5.0,
    15.0,
    30.0,
    60.0,
    120.0,
    300.0,
    600.0,
    1800.0,
    3600.0,
    21600.0,
    86400.0,
    259200.0,
    604800.0,
)


def _meter() -> metrics.Meter:
    return metrics.get_meter(__name__)


def record_case_closed(outcome: str, escalation_reason: str | None, duration: timedelta) -> None:
    attributes = {OUTCOME_ATTRIBUTE: outcome}
    if escalation_reason is not None:
        attributes[ESCALATION_REASON_ATTRIBUTE] = escalation_reason
    _meter().create_counter(
        CASES, unit="{case}", description="KYC cases closed, by outcome and escalation reason"
    ).add(1, attributes)
    _meter().create_histogram(
        CASE_DURATION,
        unit="s",
        description="Time from case creation to close, in workflow time",
        explicit_bucket_boundaries_advisory=WAIT_BUCKETS_SECONDS,
    ).record(duration.total_seconds(), {OUTCOME_ATTRIBUTE: outcome})


def record_resubmission(document_type: str) -> None:
    _meter().create_counter(
        RESUBMISSIONS, unit="{document}", description="Documents the applicant was asked to resend"
    ).add(1, {DOCUMENT_TYPE_ATTRIBUTE: document_type})


def record_review_wait(decision: ReviewWaitDecision, wait: timedelta) -> None:
    _meter().create_histogram(
        REVIEW_WAIT,
        unit="s",
        description="Time an escalated case waited for a reviewer, until a decision or expiry",
        explicit_bucket_boundaries_advisory=WAIT_BUCKETS_SECONDS,
    ).record(wait.total_seconds(), {REVIEW_DECISION_ATTRIBUTE: decision})


def record_sanctions_check(result: SanctionsCheckResult) -> None:
    _meter().create_counter(
        SANCTIONS_CHECKS, unit="{check}", description="Sanctions screenings, by result"
    ).add(1, {SANCTIONS_RESULT_ATTRIBUTE: result})
