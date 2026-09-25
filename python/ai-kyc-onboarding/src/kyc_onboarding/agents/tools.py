import asyncio
import json
from datetime import date
from typing import Annotated

from opentelemetry import trace
from pydantic import BeforeValidator
from pydantic_ai import RunContext
from temporalio import activity

# Runtime imports, not `TYPE_CHECKING`: `Agent` resolves the tool annotations with
# `get_type_hints()` to build each call schema.
from kyc_onboarding import case_metrics
from kyc_onboarding.agents.deps import AssessmentDeps  # noqa: TC001
from kyc_onboarding.agents.faults import log_injected_fault, should_raise_sanctions_down
from kyc_onboarding.attributes import (
    ACTIVITY_ATTEMPT_ATTRIBUTE,
    CASE_ID_ATTRIBUTE,
    SANCTIONS_RESULT_ATTRIBUTE,
    SANCTIONS_SCORE_ATTRIBUTE,
)
from kyc_onboarding.models.documents import (  # noqa: TC001
    ExtractedIdFields,
    ExtractedProofOfAddressFields,
    ExtractedRegistrationCertificateFields,
)
from kyc_onboarding.models.enums import CaseFault
from kyc_onboarding.tools import ExpiryCheck, IdentityCheck, SanctionsScreeningResult  # noqa: TC001
from kyc_onboarding.tools.expiry import check_expiry as _check_expiry
from kyc_onboarding.tools.identity import compare_identity as _compare_identity
from kyc_onboarding.tools.sanctions import screen_sanctions as _screen_sanctions


async def check_expiry(ctx: RunContext[AssessmentDeps], expiry_date: date | None) -> ExpiryCheck:
    return _check_expiry(expiry_date, ctx.deps.reference_date)


def _decode_json_object_string(value: object) -> object:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return value
    return value


_ACCEPTS_JSON_STRING = BeforeValidator(_decode_json_object_string)


async def compare_identity(
    ctx: RunContext[AssessmentDeps],
    id_fields: Annotated[ExtractedIdFields | None, _ACCEPTS_JSON_STRING] = None,
    proof_of_address_fields: Annotated[
        ExtractedProofOfAddressFields | None, _ACCEPTS_JSON_STRING
    ] = None,
    registration_certificate_fields: Annotated[
        ExtractedRegistrationCertificateFields | None, _ACCEPTS_JSON_STRING
    ] = None,
) -> IdentityCheck:
    """Compare names, dates of birth and addresses across the documents. Small local models
    often send each document's fields as a JSON string, so each argument is decoded before
    validation rather than costing a retry."""
    return _compare_identity(id_fields, proof_of_address_fields, registration_certificate_fields)


async def screen_sanctions(ctx: RunContext[AssessmentDeps], name: str) -> SanctionsScreeningResult:
    """Screen a name against the sanctions list. `sanctions_down` is injected here by attempt,
    from `ctx.deps.fault`. The lookup blocks on psycopg, so it runs in a thread. Every
    screening counts once in `base14.kyc.sanctions.checks`, failed ones included, and puts its
    result and score, never the matched name, on the current span, the tool's `RunActivity`."""
    if activity.in_activity():
        info = activity.info()
        if should_raise_sanctions_down(ctx.deps.fault, info.attempt):
            log_injected_fault(CaseFault.sanctions_down, info)
            _record_screening("error")
            raise ConnectionError(f"sanctions service unreachable (attempt {info.attempt})")
    try:
        screening = await asyncio.to_thread(_screen_sanctions, name, ctx.deps.dsn)
    except Exception:
        activity.logger.exception("sanctions lookup failed", extra=_activity_log_attributes())
        _record_screening("error")
        raise
    if screening.result == "partial":
        activity.logger.warning(
            "sanctions near match",
            extra={
                **_activity_log_attributes(),
                SANCTIONS_SCORE_ATTRIBUTE: screening.score,
            },
        )
    _record_screening(_CHECK_RESULTS[screening.result], screening.score)
    return screening


def _record_screening(
    result: case_metrics.SanctionsCheckResult, score: float | None = None
) -> None:
    span = trace.get_current_span()
    span.set_attribute(SANCTIONS_RESULT_ATTRIBUTE, result)
    if score is not None:
        span.set_attribute(SANCTIONS_SCORE_ATTRIBUTE, score)
    case_metrics.record_sanctions_check(result)


_CHECK_RESULTS: dict[str, case_metrics.SanctionsCheckResult] = {
    "clear": "clear",
    "partial": "near_match",
    "exact": "match",
}


def _activity_log_attributes() -> dict[str, object]:
    if not activity.in_activity():
        return {}
    info = activity.info()
    return {CASE_ID_ATTRIBUTE: info.workflow_id, ACTIVITY_ATTEMPT_ATTRIBUTE: info.attempt}
