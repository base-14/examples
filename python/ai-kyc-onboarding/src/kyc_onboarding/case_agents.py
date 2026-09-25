"""The agents a worker runs cases with, installed once at worker startup.

An agent with `TemporalDurability` is built outside the workflow so its activities can be
registered with the worker. The workflow imports this module through the sandbox
passthrough and sees the same instances.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from pydantic_ai import Agent


if TYPE_CHECKING:
    from kyc_onboarding.agents.deps import AssessmentDeps
    from kyc_onboarding.agents.prompts import PromptPair
    from kyc_onboarding.models.decisions import AssessmentDecision
    from kyc_onboarding.models.documents import ExtractedFields


@dataclass(frozen=True)
class CaseAgents:
    extraction: Agent[None, ExtractedFields]
    assessment: Agent[AssessmentDeps, AssessmentDecision]
    extraction_prompt: PromptPair
    assessment_prompt: PromptPair
    extraction_prompt_version: str
    assessment_prompt_version: str
    sanctions_dsn: str


_installed: CaseAgents | None = None


def install_case_agents(agents: CaseAgents) -> None:
    global _installed
    _installed = agents


def installed_case_agents() -> CaseAgents:
    if _installed is None:
        raise RuntimeError("no case agents installed; the worker installs them at startup")
    return _installed
