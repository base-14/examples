"""Model digests from Ollama, read once at startup for the agents' trace attributes."""

import logging

import httpx


UNKNOWN_DIGEST = "unknown"
SHORT_DIGEST_LENGTH = 12

logger = logging.getLogger(__name__)


def read_model_digests(client: httpx.Client, models: list[str]) -> dict[str, str]:
    """Map each model tag to the short digest `ollama list` shows. A model Ollama does not
    have, or an Ollama that does not answer, reads `unknown`; the agent run reports the
    failure itself."""
    digests = dict.fromkeys(models, UNKNOWN_DIGEST)
    try:
        response = client.get("/api/tags")
        response.raise_for_status()
        listed = response.json().get("models", [])
    except (httpx.HTTPError, ValueError) as error:
        logger.warning("Could not read model digests from Ollama: %s", error)
        return digests
    for entry in listed:
        for tag in {entry.get("name"), entry.get("model")}:
            if tag in digests and entry.get("digest"):
                digests[tag] = str(entry["digest"])[:SHORT_DIGEST_LENGTH]
    return digests
