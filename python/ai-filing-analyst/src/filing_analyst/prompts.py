"""System prompts, one YAML file per agent and version under `prompts/`.

A version is the UTC time the prompt was written, as the filename's prefix:
`202609261523_analyst.yaml`. Versions sort by time, so with no version set the newest file is used.
"""

import re
from dataclasses import dataclass
from pathlib import Path

import yaml


PROMPTS_DIR = Path("prompts")
VERSION_PATTERN = re.compile(r"^\d{12}$")


@dataclass(frozen=True)
class Prompt:
    name: str
    version: str
    system: str


def _newest_version(prompts_dir: Path, name: str) -> str:
    versions = sorted(
        version
        for path in prompts_dir.glob(f"*_{name}.yaml")
        if VERSION_PATTERN.match(version := path.stem.removesuffix(f"_{name}"))
    )
    if not versions:
        raise FileNotFoundError(f"No {name} prompt in {prompts_dir}")
    return versions[-1]


def load_prompt(prompts_dir: Path, name: str, version: str | None = None) -> Prompt:
    """Read `{version}_{name}.yaml`, a list of messages with one `system` entry. With no
    version, read the newest."""
    if version is None:
        version = _newest_version(prompts_dir, name)
    elif not VERSION_PATTERN.match(version):
        raise ValueError(f"Prompt version {version!r} is not a YYYYMMDDHHMM timestamp.")
    path = prompts_dir / f"{version}_{name}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"No prompt {path}")
    messages = yaml.safe_load(path.read_text())
    (system,) = [m["content"] for m in messages if m.get("role") == "system"]
    return Prompt(name=name, version=version, system=str(system).strip())
