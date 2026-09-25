from datetime import timedelta

from pydantic_ai import Agent
from pydantic_ai.durable_exec.temporal import TemporalDurability
from pydantic_ai.models.openai import OpenAIChatModel, OpenAIChatModelSettings
from pydantic_ai.profiles.openai import OpenAIJsonSchemaTransformer, OpenAIModelProfile
from pydantic_ai.providers.ollama import OllamaProvider
from temporalio.common import RetryPolicy
from temporalio.workflow import ActivityConfig

from kyc_onboarding.agents.faults import FaultInjectingModel, FaultRegistry
from kyc_onboarding.models.documents import (
    ExtractedFields,
    ExtractedIdFields,
    ExtractedProofOfAddressFields,
    ExtractedRegistrationCertificateFields,
)


# Small local models often need two tries at valid output.
OUTPUT_RETRIES = 2

# Sized for local Ollama, where a cold model can take over a minute. `TemporalDurability`
# adds the non-retryable error types.
MODEL_ACTIVITY_CONFIG: ActivityConfig = ActivityConfig(
    start_to_close_timeout=timedelta(seconds=120),
    retry_policy=RetryPolicy(
        initial_interval=timedelta(seconds=2),
        backoff_coefficient=2.0,
        maximum_interval=timedelta(seconds=30),
        maximum_attempts=5,
    ),
)

# Extraction and assessment are classification tasks, so sampling stays greedy.
TEMPERATURE = 0.0
# The largest response seen across the harness scenarios was 324 output tokens, an
# assessment answer with its reasons. The cap leaves roughly three times that.
MAX_TOKENS = 1024

TOOL_ACTIVITY_CONFIG: ActivityConfig = ActivityConfig(
    start_to_close_timeout=timedelta(seconds=30),
    retry_policy=RetryPolicy(
        initial_interval=timedelta(seconds=1),
        backoff_coefficient=2.0,
        maximum_interval=timedelta(seconds=10),
        maximum_attempts=5,
    ),
)


def build_ollama_model(
    base_url: str,
    model_name: str,
    faults: FaultRegistry,
    *,
    injects_bad_output: bool = True,
) -> FaultInjectingModel:
    """Build the model behind an agent, wrapped for fault injection.

    `OllamaProvider` talks to local Ollama through its OpenAI-compatible endpoint, so GenAI
    spans name `ollama` as the provider. `openai_reasoning_effort="none"` turns thinking off,
    which cut an extraction from about 82s to 3s locally. `supports_json_object_output=False`
    stops `PromptedOutput` from sending a `response_format`, under which Ollama never emits a
    tool call. Ollama ignores `max_completion_tokens`, so the profile sends the cap as
    `max_tokens`. It also keeps OpenAI's schema transformer: with `OllamaProvider`'s,
    gemma4:e2b drops the ID expiry date.
    """
    provider = OllamaProvider(base_url=f"{base_url}/v1")
    profile = OpenAIModelProfile(
        supports_json_object_output=False,
        openai_chat_supports_max_completion_tokens=False,
        json_schema_transformer=OpenAIJsonSchemaTransformer,
    )
    return FaultInjectingModel(
        OpenAIChatModel(
            model_name,
            provider=provider,
            settings=OpenAIChatModelSettings(
                openai_reasoning_effort="none", temperature=TEMPERATURE, max_tokens=MAX_TOKENS
            ),
            profile=profile,
        ),
        faults=faults,
        injects_bad_output=injects_bad_output,
    )


def build_extraction_agent(
    *,
    instructions: str,
    base_url: str,
    model_name: str,
    faults: FaultRegistry,
) -> Agent[None, ExtractedFields]:
    """Build the extraction agent, which reads one document and returns its typed fields.
    `instructions` is the loaded prompt text; this function does no file I/O."""
    return Agent(
        build_ollama_model(base_url, model_name, faults),
        name="kyc-extraction",
        description="Reads one KYC document and returns its fields for that document type.",
        retries={"output": OUTPUT_RETRIES},
        # A list of the union's members: mypy cannot match the bare `ExtractedFields` alias
        # against the `Agent` overloads.
        output_type=[
            ExtractedIdFields,
            ExtractedProofOfAddressFields,
            ExtractedRegistrationCertificateFields,
        ],
        instructions=instructions,
        capabilities=[
            TemporalDurability[None](
                activity_config=TOOL_ACTIVITY_CONFIG,
                model_activity_config=MODEL_ACTIVITY_CONFIG,
            )
        ],
    )
