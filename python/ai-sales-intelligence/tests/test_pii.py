"""Tests for PII scrubbing utilities."""

from sales_intelligence.pii import (
    CREDIT_CARD_PATTERN,
    EMAIL_PATTERN,
    LINKEDIN_PATTERN,
    PHONE_PATTERN,
    SSN_PATTERN,
    scrub_completion,
    scrub_pii,
    scrub_prompt,
)


class TestEmailScrubbing:
    """Test email PII scrubbing."""

    def test_scrubs_simple_email(self) -> None:
        text = "Contact john@example.com for info"
        result = scrub_pii(text, [EMAIL_PATTERN])
        assert result == "Contact [EMAIL] for info"

    def test_scrubs_multiple_emails(self) -> None:
        text = "Email john@example.com or jane@company.org"
        result = scrub_pii(text, [EMAIL_PATTERN])
        assert result == "Email [EMAIL] or [EMAIL]"

    def test_scrubs_email_with_plus(self) -> None:
        text = "Contact john+test@example.com"
        result = scrub_pii(text, [EMAIL_PATTERN])
        assert result == "Contact [EMAIL]"


class TestPhoneScrubbing:
    """Test phone number PII scrubbing."""

    def test_scrubs_simple_phone(self) -> None:
        text = "Call 555-123-4567 now"
        result = scrub_pii(text, [PHONE_PATTERN])
        assert result == "Call [PHONE] now"

    def test_scrubs_phone_with_parens(self) -> None:
        text = "Call (555) 123-4567"
        result = scrub_pii(text, [PHONE_PATTERN])
        assert result == "Call [PHONE]"

    def test_scrubs_phone_with_country_code(self) -> None:
        text = "Call +1-555-123-4567"
        result = scrub_pii(text, [PHONE_PATTERN])
        assert result == "Call [PHONE]"


class TestLinkedInScrubbing:
    """Test LinkedIn URL scrubbing."""

    def test_scrubs_linkedin_url(self) -> None:
        text = "Profile: https://linkedin.com/in/johndoe"
        result = scrub_pii(text, [LINKEDIN_PATTERN])
        assert result == "Profile: [LINKEDIN_URL]"

    def test_scrubs_linkedin_with_www(self) -> None:
        text = "See https://www.linkedin.com/in/jane-doe-123"
        result = scrub_pii(text, [LINKEDIN_PATTERN])
        assert result == "See [LINKEDIN_URL]"


class TestSSNScrubbing:
    """Test SSN scrubbing."""

    def test_scrubs_ssn_with_dashes(self) -> None:
        text = "SSN: 123-45-6789"
        result = scrub_pii(text, [SSN_PATTERN])
        assert result == "SSN: [SSN]"

    def test_scrubs_ssn_without_dashes(self) -> None:
        text = "SSN: 123456789"
        result = scrub_pii(text, [SSN_PATTERN])
        assert result == "SSN: [SSN]"


class TestCreditCardScrubbing:
    """Test credit card scrubbing."""

    def test_scrubs_cc_with_spaces(self) -> None:
        text = "Card: 4111 1111 1111 1111"
        result = scrub_pii(text, [CREDIT_CARD_PATTERN])
        assert result == "Card: [CREDIT_CARD]"

    def test_scrubs_cc_with_dashes(self) -> None:
        text = "Card: 4111-1111-1111-1111"
        result = scrub_pii(text, [CREDIT_CARD_PATTERN])
        assert result == "Card: [CREDIT_CARD]"


class TestFullScrubbing:
    """Test full PII scrubbing with all patterns."""

    def test_scrubs_mixed_pii(self) -> None:
        text = """
        Contact john@example.com at 555-123-4567.
        LinkedIn: https://linkedin.com/in/johndoe
        """
        result = scrub_pii(text)
        assert "[EMAIL]" in result
        assert "[PHONE]" in result
        assert "[LINKEDIN_URL]" in result
        assert "john@example.com" not in result
        assert "555-123-4567" not in result

    def test_empty_string(self) -> None:
        assert scrub_pii("") == ""

    def test_no_pii(self) -> None:
        text = "This text has no PII"
        assert scrub_pii(text) == text


class TestPromptAndCompletionScrubbing:
    """Test prompt and completion wrapper functions."""

    def test_scrub_prompt(self) -> None:
        prompt = "Research john@example.com at Acme Corp"
        result = scrub_prompt(prompt)
        assert "[EMAIL]" in result
        assert "john@example.com" not in result

    def test_scrub_completion(self) -> None:
        completion = "Found contact: jane@company.com, 555-999-8888"
        result = scrub_completion(completion)
        assert "[EMAIL]" in result
        assert "[PHONE]" in result
