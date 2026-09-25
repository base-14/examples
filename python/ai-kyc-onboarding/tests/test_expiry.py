from datetime import date

from kyc_onboarding.tools.expiry import check_expiry


REFERENCE_DATE = date(2026, 9, 24)


class TestCheckExpiry:
    def test_expires_today_is_valid(self) -> None:
        result = check_expiry(REFERENCE_DATE, REFERENCE_DATE)
        assert result.status == "valid"
        assert result.expired is False
        assert result.expiry_date == REFERENCE_DATE

    def test_expired_yesterday_is_expired(self) -> None:
        result = check_expiry(date(2026, 9, 23), REFERENCE_DATE)
        assert result.status == "expired"
        assert result.expired is True

    def test_far_future_is_valid(self) -> None:
        result = check_expiry(date(2040, 1, 1), REFERENCE_DATE)
        assert result.status == "valid"
        assert result.expired is False

    def test_missing_expiry_date_is_reported_missing_not_expired(self) -> None:
        result = check_expiry(None, REFERENCE_DATE)
        assert result.status == "missing"
        assert result.expired is False
        assert result.expiry_date is None

    def test_reference_date_is_carried_through(self) -> None:
        result = check_expiry(date(2026, 9, 23), REFERENCE_DATE)
        assert result.reference_date == REFERENCE_DATE
