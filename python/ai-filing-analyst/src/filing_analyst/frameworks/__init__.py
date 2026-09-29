"""One adapter per agent framework. `FILING_FRAMEWORK` picks one, and only its module is
imported, since each framework is installed as its own extra with its own OpenTelemetry pins."""

import importlib
from typing import TYPE_CHECKING, cast


if TYPE_CHECKING:
    from filing_analyst.agents import Framework
    from filing_analyst.config import Settings


ADAPTERS = {
    "strands": "strands",
    "adk": "adk",
    "maf": "maf",
    "openai-agents": "openai_agents",
}


def load_framework(settings: Settings) -> Framework:
    module_name = ADAPTERS.get(settings.framework)
    if module_name is None:
        raise ValueError(f"FILING_FRAMEWORK is one of {', '.join(ADAPTERS)}.")
    module = importlib.import_module(f"{__name__}.{module_name}")
    return cast("Framework", module.from_settings(settings))
