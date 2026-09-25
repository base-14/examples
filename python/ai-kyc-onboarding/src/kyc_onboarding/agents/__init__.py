"""The extraction and assessment agents, their tools, prompts, and fault injection.

Nothing here reads a file or the environment at import time, so the Temporal workflow
sandbox can re-import the package. Prompt text and settings come from the caller.
"""

from kyc_onboarding.agents.assessment import build_assessment_agent
from kyc_onboarding.agents.deps import AssessmentDeps
from kyc_onboarding.agents.extraction import (
    MODEL_ACTIVITY_CONFIG,
    TOOL_ACTIVITY_CONFIG,
    build_extraction_agent,
    build_ollama_model,
)
from kyc_onboarding.agents.faults import (
    FaultInjectingModel,
    FaultRegistry,
    PostgresFaultRegistry,
    StaticFaultRegistry,
    should_raise_model_unavailable,
    should_raise_sanctions_down,
)
from kyc_onboarding.agents.prompts import PROMPT_VERSION_METADATA_KEY, PromptPair, load_prompt


__all__ = [
    "MODEL_ACTIVITY_CONFIG",
    "PROMPT_VERSION_METADATA_KEY",
    "TOOL_ACTIVITY_CONFIG",
    "AssessmentDeps",
    "FaultInjectingModel",
    "FaultRegistry",
    "PostgresFaultRegistry",
    "PromptPair",
    "StaticFaultRegistry",
    "build_assessment_agent",
    "build_extraction_agent",
    "build_ollama_model",
    "load_prompt",
    "should_raise_model_unavailable",
    "should_raise_sanctions_down",
]
