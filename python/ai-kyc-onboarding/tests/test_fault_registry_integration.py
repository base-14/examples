import os

import psycopg
import pytest

from kyc_onboarding.agents.faults import PostgresFaultRegistry
from kyc_onboarding.models.enums import CaseFault


pytestmark = pytest.mark.integration

KYC_TEST_DSN = os.environ.get("KYC_TEST_DSN", "postgresql://temporal:temporal@localhost:5433/kyc")


@pytest.fixture
def seeded_case(request: pytest.FixtureRequest) -> str:
    case_id = f"fault-registry-{request.node.name}"
    with psycopg.connect(KYC_TEST_DSN, connect_timeout=5) as connection:
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM case_faults WHERE case_id = %s", (case_id,))
            cursor.execute(
                "INSERT INTO case_faults (case_id, fault) VALUES (%s, %s)",
                (case_id, CaseFault.bad_output.value),
            )
        connection.commit()
    return case_id


class TestPostgresFaultRegistry:
    def test_fault_for_reads_the_seeded_fault(self, seeded_case: str) -> None:
        registry = PostgresFaultRegistry(KYC_TEST_DSN)

        assert registry.fault_for(seeded_case) == CaseFault.bad_output

    def test_fault_for_returns_none_for_an_unseeded_case(self) -> None:
        registry = PostgresFaultRegistry(KYC_TEST_DSN)

        assert registry.fault_for("no-such-case") is None

    def test_consume_once_claims_the_first_call_only(self, seeded_case: str) -> None:
        registry = PostgresFaultRegistry(KYC_TEST_DSN)

        assert registry.consume_once(seeded_case, CaseFault.bad_output) is True
        assert registry.consume_once(seeded_case, CaseFault.bad_output) is False

    def test_consume_once_returns_false_for_an_unseeded_case(self) -> None:
        registry = PostgresFaultRegistry(KYC_TEST_DSN)

        assert registry.consume_once("no-such-case", CaseFault.bad_output) is False


class TestPostgresFaultRegistryRecordFault:
    def test_record_fault_writes_a_row_the_registry_can_read_back(
        self, request: pytest.FixtureRequest
    ) -> None:
        case_id = f"fault-registry-{request.node.name}"
        with psycopg.connect(KYC_TEST_DSN, connect_timeout=5) as connection:
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM case_faults WHERE case_id = %s", (case_id,))
            connection.commit()
        registry = PostgresFaultRegistry(KYC_TEST_DSN)

        registry.record_fault(case_id, CaseFault.tight_budget)

        assert registry.fault_for(case_id) == CaseFault.tight_budget

    def test_record_fault_is_idempotent_for_the_same_case_and_fault(
        self, request: pytest.FixtureRequest
    ) -> None:
        case_id = f"fault-registry-{request.node.name}"
        with psycopg.connect(KYC_TEST_DSN, connect_timeout=5) as connection:
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM case_faults WHERE case_id = %s", (case_id,))
            connection.commit()
        registry = PostgresFaultRegistry(KYC_TEST_DSN)

        registry.record_fault(case_id, CaseFault.tight_budget)
        registry.record_fault(case_id, CaseFault.tight_budget)

        assert registry.fault_for(case_id) == CaseFault.tight_budget
