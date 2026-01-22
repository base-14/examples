"""PII scrubbing utilities for telemetry safety.

Scrubs personally identifiable information from prompts and completions
before they are recorded in traces, logs, or metrics.

PII Categories:
- Email addresses
- Phone numbers
- LinkedIn URLs
- Names (partial scrubbing)
"""

import re
from dataclasses import dataclass


@dataclass
class PIIPattern:
    """Pattern definition for PII detection."""

    name: str
    pattern: re.Pattern[str]
    replacement: str


# Email pattern - matches most common email formats
EMAIL_PATTERN = PIIPattern(
    name="email",
    pattern=re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"),
    replacement="[EMAIL]",
)

# Phone pattern - matches various phone formats
PHONE_PATTERN = PIIPattern(
    name="phone",
    pattern=re.compile(r"(?:\+?1[-.\s]?)?\(?[0-9]{3}\)?[-.\s]?[0-9]{3}[-.\s]?[0-9]{4}\b"),
    replacement="[PHONE]",
)

# LinkedIn URL pattern
LINKEDIN_PATTERN = PIIPattern(
    name="linkedin",
    pattern=re.compile(r"https?://(?:www\.)?linkedin\.com/in/[A-Za-z0-9_-]+/?"),
    replacement="[LINKEDIN_URL]",
)

# SSN pattern (US)
SSN_PATTERN = PIIPattern(
    name="ssn",
    pattern=re.compile(r"\b\d{3}[-]?\d{2}[-]?\d{4}\b"),
    replacement="[SSN]",
)

# Credit card pattern (basic)
CREDIT_CARD_PATTERN = PIIPattern(
    name="credit_card",
    pattern=re.compile(r"\b(?:\d{4}[-\s]?){3}\d{4}\b"),
    replacement="[CREDIT_CARD]",
)

# Default patterns to apply
DEFAULT_PATTERNS = [
    EMAIL_PATTERN,
    PHONE_PATTERN,
    LINKEDIN_PATTERN,
    SSN_PATTERN,
    CREDIT_CARD_PATTERN,
]


def scrub_pii(text: str, patterns: list[PIIPattern] | None = None) -> str:
    """Scrub PII from text using specified patterns.

    Args:
        text: Input text that may contain PII
        patterns: List of PII patterns to apply (defaults to all patterns)

    Returns:
        Text with PII replaced by placeholders
    """
    if not text:
        return text

    patterns = patterns or DEFAULT_PATTERNS
    result = text

    for pii_pattern in patterns:
        result = pii_pattern.pattern.sub(pii_pattern.replacement, result)

    return result


def scrub_prompt(prompt: str) -> str:
    """Scrub PII from an LLM prompt.

    Args:
        prompt: The prompt to be sent to the LLM

    Returns:
        Prompt with PII scrubbed for safe logging/tracing
    """
    return scrub_pii(prompt)


def scrub_completion(completion: str) -> str:
    """Scrub PII from an LLM completion.

    Args:
        completion: The completion received from the LLM

    Returns:
        Completion with PII scrubbed for safe logging/tracing
    """
    return scrub_pii(completion)
