from runbook_assistant.pii import scrub


def test_scrubs_email():
    assert "alice@example.com" not in scrub("contact alice@example.com now")
    assert "[email]" in scrub("contact alice@example.com now")


def test_scrubs_ip():
    assert "10.1.2.3" not in scrub("host 10.1.2.3 down")


def test_truncates():
    assert len(scrub("x" * 5000, limit=100)) <= 100
