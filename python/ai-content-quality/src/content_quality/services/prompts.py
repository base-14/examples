from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml


PROMPTS_DIR = Path(__file__).resolve().parents[3] / "prompts"


@dataclass(frozen=True)
class PromptPair:
    system: str
    user: str


@lru_cache
def load_prompt(name: str) -> PromptPair:
    path = PROMPTS_DIR / f"{name}.yaml"
    with path.open() as f:
        messages: list[dict[str, str]] = yaml.safe_load(f)

    system = ""
    user = ""
    for msg in messages:
        text = msg["content"].replace("{{", "{").replace("}}", "}")
        if msg["role"] == "system":
            system = text
        elif msg["role"] == "user":
            user = text

    return PromptPair(system=system, user=user)
