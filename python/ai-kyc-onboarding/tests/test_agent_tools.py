from collections.abc import Sequence
from dataclasses import replace
from datetime import date

import pytest
from opentelemetry.sdk._logs import ReadableLogRecord
from pydantic_ai import RunContext
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.usage import RunUsage
from temporalio.testing import ActivityEnvironment

from kyc_onboarding.agents.deps import AssessmentDeps
from kyc_onboarding.agents.tools import check_expiry, compare_identity, screen_sanctions
from kyc_onboarding.attributes import (
    ACTIVITY_ATTEMPT_ATTRIBUTE,
    CASE_ID_ATTRIBUTE,
    SANCTIONS_RESULT_ATTRIBUTE,
    SANCTIONS_SCORE_ATTRIBUTE,
)
from kyc_onboarding.case_metrics import SANCTIONS_CHECKS
from kyc_onboarding.models.documents import ExtractedIdFields
from kyc_onboarding.models.enums import CaseFault
from kyc_onboarding.tools import SanctionsScreeningResult
from tests._telemetry_support import captured_logs, counter_value, log_attribute, log_body


CLEAR = SanctionsScreeningResult(result="clear", matched_entry=None, score=None)


def _run_context(deps: AssessmentDeps) -> RunContext[AssessmentDeps]:
    def _unused(messages, info):  # type: ignore[no-untyped-def]
        raise NotImplementedError

    return RunContext(deps=deps, model=FunctionModel(_unused), usage=RunUsage())


def _activity_env(*, workflow_id: str, attempt: int) -> ActivityEnvironment:
    env = ActivityEnvironment()
    env.info = replace(env.info, workflow_id=workflow_id, attempt=attempt)
    return env


class TestCheckExpiry:
    async def test_compares_against_the_deps_reference_date(self) -> None:
        deps = AssessmentDeps(dsn="postgresql://x", reference_date=date(2026, 1, 1))
        ctx = _run_context(deps)

        result = await check_expiry(ctx, date(2020, 1, 1))

        assert result.expired is True
        assert result.reference_date == date(2026, 1, 1)


class TestCompareIdentity:
    async def test_delegates_to_the_plain_function(self) -> None:
        deps = AssessmentDeps(dsn="postgresql://x", reference_date=date(2026, 1, 1))
        ctx = _run_context(deps)
        id_fields = ExtractedIdFields(
            full_name="Jane Doe", date_of_birth=date(1990, 1, 1), id_number="X1"
        )

        result = await compare_identity(ctx, id_fields=id_fields)

        assert result.match is True


class TestScreenSanctionsOutsideAnActivity:
    async def test_calls_through_without_checking_the_fault(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[tuple[str, str]] = []

        def fake_screen(name: str, dsn: str) -> SanctionsScreeningResult:
            calls.append((name, dsn))
            return CLEAR

        monkeypatch.setattr("kyc_onboarding.agents.tools._screen_sanctions", fake_screen)
        deps = AssessmentDeps(
            dsn="postgresql://x", reference_date=date(2026, 1, 1), fault=CaseFault.sanctions_down
        )
        ctx = _run_context(deps)

        await screen_sanctions(ctx, "Jane Doe")

        assert calls == [("Jane Doe", "postgresql://x")]


class TestScreenSanctionsInsideAnActivity:
    async def test_raises_sanctions_down_on_early_attempts(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "kyc_onboarding.agents.tools._screen_sanctions",
            lambda *_a, **_k: pytest.fail("should not reach the tool body"),
        )
        deps = AssessmentDeps(
            dsn="postgresql://x", reference_date=date(2026, 1, 1), fault=CaseFault.sanctions_down
        )
        ctx = _run_context(deps)
        env = _activity_env(workflow_id="case-1", attempt=1)

        with pytest.raises(ConnectionError):
            await env.run(screen_sanctions, ctx, "Jane Doe")

    async def test_calls_through_once_the_fault_stops_raising(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[tuple[str, str]] = []

        def fake_screen(name: str, dsn: str) -> SanctionsScreeningResult:
            calls.append((name, dsn))
            return CLEAR

        monkeypatch.setattr("kyc_onboarding.agents.tools._screen_sanctions", fake_screen)
        deps = AssessmentDeps(
            dsn="postgresql://x", reference_date=date(2026, 1, 1), fault=CaseFault.sanctions_down
        )
        ctx = _run_context(deps)
        env = _activity_env(workflow_id="case-1", attempt=10)

        await env.run(screen_sanctions, ctx, "Jane Doe")

        assert calls == [("Jane Doe", "postgresql://x")]

    async def test_a_different_fault_never_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[tuple[str, str]] = []
        monkeypatch.setattr(
            "kyc_onboarding.agents.tools._screen_sanctions",
            lambda name, dsn: calls.append((name, dsn)) or CLEAR,
        )
        deps = AssessmentDeps(
            dsn="postgresql://x", reference_date=date(2026, 1, 1), fault=CaseFault.model_unavailable
        )
        ctx = _run_context(deps)
        env = _activity_env(workflow_id="case-1", attempt=1)

        await env.run(screen_sanctions, ctx, "Jane Doe")

        assert calls == [("Jane Doe", "postgresql://x")]


class TestScreenSanctionsTelemetry:
    @pytest.mark.parametrize(
        ("screened", "counted"),
        [("clear", "clear"), ("partial", "near_match"), ("exact", "match")],
    )
    async def test_counts_each_screening_by_result(
        self, monkeypatch: pytest.MonkeyPatch, screened: str, counted: str
    ) -> None:
        screening = SanctionsScreeningResult.model_validate(
            {"result": screened, "matched_entry": "Maria Gonzales", "score": 0.6}
        )
        monkeypatch.setattr("kyc_onboarding.agents.tools._screen_sanctions", lambda *_: screening)
        before = _sanctions_checks(counted)

        await _activity_env(workflow_id="case-1", attempt=1).run(
            screen_sanctions, _run_context(_deps()), "Maria Gonzalez"
        )

        assert _sanctions_checks(counted) == before + 1

    async def test_a_near_match_logs_a_warning(self, monkeypatch: pytest.MonkeyPatch) -> None:
        partial = SanctionsScreeningResult(
            result="partial", matched_entry="Maria Gonzales", score=0.6
        )
        monkeypatch.setattr("kyc_onboarding.agents.tools._screen_sanctions", lambda *_: partial)
        with captured_logs() as logs:
            await _activity_env(workflow_id="case-near-match", attempt=1).run(
                screen_sanctions, _run_context(_deps()), "Maria Gonzalez"
            )
        (record,) = _case_lines(logs.get_finished_logs(), "case-near-match")

        assert log_body(record) == "sanctions near match"
        assert record.log_record.severity_text == "WARN"
        assert log_attribute(record, SANCTIONS_SCORE_ATTRIBUTE) == 0.6
        assert "Maria Gonzales" not in str(record.log_record.attributes)

    async def test_an_injected_fault_counts_an_error_and_logs_the_attempt(self) -> None:
        before = _sanctions_checks("error")
        with captured_logs() as logs, pytest.raises(ConnectionError):
            await _activity_env(workflow_id="case-injected", attempt=2).run(
                screen_sanctions, _run_context(_deps(CaseFault.sanctions_down)), "Maria Gonzalez"
            )
        (record,) = _case_lines(logs.get_finished_logs(), "case-injected")

        assert _sanctions_checks("error") == before + 1
        assert log_body(record) == "injected sanctions_down fault"
        assert record.log_record.severity_text == "ERROR"
        assert log_attribute(record, ACTIVITY_ATTEMPT_ATTRIBUTE) == 2

    async def test_a_lookup_failure_counts_an_error_and_logs_the_exception(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def unreachable(name: str, dsn: str) -> SanctionsScreeningResult:
            raise OSError("connection refused")

        monkeypatch.setattr("kyc_onboarding.agents.tools._screen_sanctions", unreachable)
        before = _sanctions_checks("error")
        with captured_logs() as logs, pytest.raises(OSError):
            await _activity_env(workflow_id="case-lookup-failed", attempt=3).run(
                screen_sanctions, _run_context(_deps()), "Maria Gonzalez"
            )
        (record,) = _case_lines(logs.get_finished_logs(), "case-lookup-failed")

        assert _sanctions_checks("error") == before + 1
        assert log_body(record) == "sanctions lookup failed"
        assert record.log_record.severity_text == "ERROR"
        assert log_attribute(record, ACTIVITY_ATTEMPT_ATTRIBUTE) == 3
        assert log_attribute(record, "exception.type") == "OSError"


def _deps(fault: CaseFault | None = None) -> AssessmentDeps:
    return AssessmentDeps(dsn="postgresql://x", reference_date=date(2026, 1, 1), fault=fault)


def _sanctions_checks(result: str) -> int:
    return counter_value(SANCTIONS_CHECKS, {SANCTIONS_RESULT_ATTRIBUTE: result})


def _case_lines(records: Sequence[ReadableLogRecord], case_id: str) -> list[ReadableLogRecord]:
    return [record for record in records if log_attribute(record, CASE_ID_ATTRIBUTE) == case_id]
