"""Best-effort PII scrubbing for opt-in telemetry content."""

import re


_EMAIL = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
_IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_BEARER = re.compile(r"(?i)bearer\s+[a-z0-9._-]+")
_APIKEY = re.compile(r"\b(sk-|key-)[A-Za-z0-9]{8,}\b")


def scrub(text: str, limit: int = 1000) -> str:
    if not text:
        return ""
    text = _EMAIL.sub("[email]", text)
    text = _IPV4.sub("[ip]", text)
    text = _BEARER.sub("[token]", text)
    text = _APIKEY.sub("[key]", text)
    return text[:limit]
