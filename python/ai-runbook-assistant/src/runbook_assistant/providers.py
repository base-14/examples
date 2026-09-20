"""Provider identity for telemetry: semconv names and server endpoints.

`LLM_PROVIDER` selects a provider by its gateway-contract key (`google` selects
Gemini). Telemetry reports the semantic convention name instead, so every
emitted `gen_ai.provider.name` goes through `semconv_name`. LangChain's own
`ls_provider` values are mapped here too, so spans read the same in `auto` mode.
"""

from urllib.parse import urlparse


OLLAMA_PORT = 11434

SEMCONV_NAMES: dict[str, str] = {
    "ollama": "ollama",
    "anthropic": "anthropic",
    "openai": "openai",
    "google": "gcp.gemini",
    "google_genai": "gcp.gemini",
    "google_vertexai": "gcp.gemini",
    "gcp.gemini": "gcp.gemini",
}

SERVERS: dict[str, tuple[str, int]] = {
    "anthropic": ("api.anthropic.com", 443),
    "openai": ("api.openai.com", 443),
    "gcp.gemini": ("generativelanguage.googleapis.com", 443),
}


def semconv_name(provider: str) -> str:
    return SEMCONV_NAMES.get(provider, provider)


def server_endpoint(provider: str, ollama_base_url: str) -> tuple[str | None, int | None]:
    """Address and port to report on a span for a semconv provider name."""
    if provider == "ollama":
        url = urlparse(ollama_base_url)
        return url.hostname or "localhost", url.port or OLLAMA_PORT
    return SERVERS.get(provider, (None, None))
