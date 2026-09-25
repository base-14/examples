from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml


PROMPT_VERSION_METADATA_KEY = "prompt_version"


def _prompts_dir() -> Path:
    # Resolved lazily: `Path.resolve()` is restricted under the workflow sandbox.
    return Path(__file__).resolve().parents[3] / "prompts"


@dataclass(frozen=True)
class PromptPair:
    system: str
    user: str


@lru_cache
def load_prompt(name: str) -> PromptPair:
    """Load a versioned prompt YAML by name, such as `extraction_v1`. Called at worker
    startup, outside the workflow sandbox."""
    path = _prompts_dir() / f"{name}.yaml"
    with path.open() as f:
        messages: list[dict[str, str]] = yaml.safe_load(f)

    system = ""
    user = ""
    for message in messages:
        text = message["content"].replace("{{", "{").replace("}}", "}")
        if message["role"] == "system":
            system = text
        elif message["role"] == "user":
            user = text

    return PromptPair(system=system, user=user)
