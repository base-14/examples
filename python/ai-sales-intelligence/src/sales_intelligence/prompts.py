"""Prompt management - loads and formats prompts from YAML config."""

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml


def _get_config_path() -> Path:
    """Get the prompts config file path."""
    env_path = os.getenv("PROMPTS_CONFIG_PATH")
    if env_path:
        return Path(env_path)

    # Default: config/prompts.yaml relative to project root
    # Try multiple locations for flexibility
    candidates = [
        Path("config/prompts.yaml"),
        Path("/app/config/prompts.yaml"),  # Docker
        Path(__file__).parent.parent.parent / "config" / "prompts.yaml",
    ]

    for candidate in candidates:
        if candidate.exists():
            return candidate

    raise FileNotFoundError(
        "prompts.yaml not found. Set PROMPTS_CONFIG_PATH or place in config/prompts.yaml"
    )


@lru_cache(maxsize=1)
def _load_config() -> dict[str, Any]:
    """Load and cache the prompts configuration."""
    config_path = _get_config_path()
    with config_path.open() as f:
        result: dict[str, Any] = yaml.safe_load(f)
        return result


def get_company_context() -> dict[str, str]:
    """Get company context for prompt interpolation."""
    config = _load_config()
    company: dict[str, str] = config.get("company", {})
    return company


def get_prompt(agent: str, prompt_type: str = "system") -> str:
    """Get a prompt template for an agent.

    Args:
        agent: Agent name (enrich, score, draft, evaluate)
        prompt_type: Prompt type (system or user)

    Returns:
        Prompt template string
    """
    config = _load_config()
    prompts = config.get("prompts", {})

    if agent not in prompts:
        raise KeyError(f"Unknown agent: {agent}")

    agent_prompts = prompts[agent]
    if prompt_type not in agent_prompts:
        raise KeyError(f"Unknown prompt type '{prompt_type}' for agent '{agent}'")

    result: str = agent_prompts[prompt_type]
    return result


def format_prompt(agent: str, prompt_type: str = "system", **kwargs: Any) -> str:
    """Get and format a prompt with provided values.

    Args:
        agent: Agent name (enrich, score, draft, evaluate)
        prompt_type: Prompt type (system or user)
        **kwargs: Values to interpolate into the prompt

    Returns:
        Formatted prompt string
    """
    template = get_prompt(agent, prompt_type)

    # Merge company context with provided kwargs (kwargs take precedence)
    context = {**get_company_context(), **kwargs}

    # Use safe formatting that ignores missing keys
    return _safe_format(template, context)


def _safe_format(template: str, values: dict[str, Any]) -> str:
    """Format template, leaving unmatched placeholders as-is.

    This allows partial formatting where some placeholders are filled
    and others are left for later formatting.
    """
    result = template
    for key, value in values.items():
        placeholder = "{" + key + "}"
        if placeholder in result:
            result = result.replace(placeholder, str(value))
    return result


def reload_config() -> None:
    """Reload the prompts configuration (clears cache)."""
    _load_config.cache_clear()
