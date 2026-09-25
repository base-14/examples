import os

import pytest

from kyc_onboarding.tools.sanctions import screen_sanctions


pytestmark = pytest.mark.integration

KYC_TEST_DSN = os.environ.get("KYC_TEST_DSN", "postgresql://temporal:temporal@localhost:5433/kyc")


class TestScreenSanctions:
    def test_clear_name_has_no_match(self) -> None:
        result = screen_sanctions("Maria Elena Gonzalez", KYC_TEST_DSN)
        assert result.result == "clear"

    def test_exact_match_on_seeded_entry(self) -> None:
        result = screen_sanctions("Nadia Karim Haddad", KYC_TEST_DSN)
        assert result.result == "exact"
        assert result.matched_entry == "Nadia Karim Haddad"
        assert result.score == 1.0

    def test_exact_match_is_case_insensitive(self) -> None:
        result = screen_sanctions("nadia karim haddad", KYC_TEST_DSN)
        assert result.result == "exact"

    def test_partial_match_on_near_miss_name(self) -> None:
        result = screen_sanctions("Alexander Petrov Volkov", KYC_TEST_DSN)
        assert result.result == "partial"
        assert result.matched_entry == "Alexander Petrov Wolkov"
        assert result.score is not None
        assert 0.0 < result.score < 1.0

    def test_shared_connection_is_not_closed_by_the_call(self) -> None:
        import psycopg

        with psycopg.connect(KYC_TEST_DSN) as connection:
            screen_sanctions("Maria Elena Gonzalez", connection)
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                assert cursor.fetchone() == (1,)
