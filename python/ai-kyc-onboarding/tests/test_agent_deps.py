from datetime import date

from pydantic import TypeAdapter

from kyc_onboarding.agents.deps import AssessmentDeps
from kyc_onboarding.models.enums import CaseFault


class TestAssessmentDeps:
    def test_fault_defaults_to_none(self) -> None:
        deps = AssessmentDeps(dsn="postgresql://x", reference_date=date(2026, 1, 1))

        assert deps.fault is None

    def test_serializes_across_the_activity_boundary(self) -> None:
        # Temporal serializes activity arguments through a `TypeAdapter` Python round trip.
        deps = AssessmentDeps(
            dsn="postgresql://user:pass@host/db",
            reference_date=date(2026, 3, 14),
            fault=CaseFault.sanctions_down,
        )
        adapter = TypeAdapter(AssessmentDeps)

        dumped = adapter.dump_python(deps)
        restored = adapter.validate_python(dumped)

        assert restored == deps

    def test_round_trips_through_json_too(self) -> None:
        deps = AssessmentDeps(dsn="postgresql://x", reference_date=date(2026, 6, 1))
        adapter = TypeAdapter(AssessmentDeps)

        restored = adapter.validate_json(adapter.dump_json(deps))

        assert restored == deps
