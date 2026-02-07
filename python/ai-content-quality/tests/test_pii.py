from content_quality.pii import scrub_pii


def test_scrubs_email() -> None:
    assert scrub_pii("Contact john@example.com for info") == "Contact [EMAIL] for info"


def test_scrubs_multiple_emails() -> None:
    text = "CC alice@test.org and bob@domain.com"
    result = scrub_pii(text)
    assert result.count("[EMAIL]") == 2
    assert "alice@" not in result


def test_scrubs_phone_with_dashes() -> None:
    assert scrub_pii("Call 555-123-4567") == "Call [PHONE]"


def test_scrubs_phone_with_dots() -> None:
    assert scrub_pii("Call 555.123.4567") == "Call [PHONE]"


def test_scrubs_phone_no_separators() -> None:
    assert scrub_pii("Call 5551234567") == "Call [PHONE]"


def test_scrubs_ssn() -> None:
    assert scrub_pii("SSN: 123-45-6789") == "SSN: [SSN]"


def test_scrubs_credit_card_with_spaces() -> None:
    assert scrub_pii("Card: 4111 1111 1111 1111") == "Card: [CARD]"


def test_scrubs_credit_card_with_dashes() -> None:
    assert scrub_pii("Card: 4111-1111-1111-1111") == "Card: [CARD]"


def test_scrubs_credit_card_no_separators() -> None:
    assert scrub_pii("Card: 4111111111111111") == "Card: [CARD]"


def test_scrubs_linkedin_url() -> None:
    assert scrub_pii("Profile: https://www.linkedin.com/in/john-doe") == "Profile: [LINKEDIN]"


def test_scrubs_linkedin_url_without_www() -> None:
    assert scrub_pii("See https://linkedin.com/in/jane-smith") == "See [LINKEDIN]"


def test_no_match_passthrough() -> None:
    text = "This is clean content with no PII."
    assert scrub_pii(text) == text


def test_empty_string() -> None:
    assert scrub_pii("") == ""


def test_multiple_pii_types() -> None:
    text = "Email john@test.com, call 555-123-4567, SSN 123-45-6789"
    result = scrub_pii(text)
    assert "[EMAIL]" in result
    assert "[PHONE]" in result
    assert "[SSN]" in result
    assert "john@" not in result
    assert "555-123" not in result
    assert "123-45" not in result
