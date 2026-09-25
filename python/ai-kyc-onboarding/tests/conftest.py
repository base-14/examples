import pytest

from kyc_onboarding.tools import SanctionsScreeningResult


@pytest.fixture
def sanctions_clear(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    screened: list[str] = []

    def screen(name: str, dsn: str) -> SanctionsScreeningResult:
        screened.append(name)
        return SanctionsScreeningResult(result="clear", matched_entry=None, score=None)

    monkeypatch.setattr("kyc_onboarding.agents.tools._screen_sanctions", screen)
    return screened
