from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import TypeAdapter, ValidationError
from pydantic_ai import Agent, ModelRetry, PromptedOutput, RunContext
from pydantic_ai.durable_exec.temporal import TemporalDurability
from pydantic_ai.messages import ToolReturnPart

from kyc_onboarding.agents.deps import AssessmentDeps
from kyc_onboarding.agents.extraction import (
    MODEL_ACTIVITY_CONFIG,
    OUTPUT_RETRIES,
    TOOL_ACTIVITY_CONFIG,
    build_ollama_model,
)
from kyc_onboarding.agents.tools import check_expiry, compare_identity, screen_sanctions
from kyc_onboarding.models.decisions import (
    ApproveDecision,
    AssessmentAnswer,
    AssessmentDecision,
    EscalateDecision,
    RequestResubmissionDecision,
)


if TYPE_CHECKING:
    from kyc_onboarding.agents.faults import FaultRegistry


# The default template opens with "Always respond with a JSON object", which competes with
# the prompt's instruction to call the tools first.
DECISION_SCHEMA_TEMPLATE = "The decision schema:\n\n{schema}"

_DECISION_ADAPTER: TypeAdapter[AssessmentDecision] = TypeAdapter(AssessmentDecision)


REQUIRED_TOOLS = ("check_expiry", "compare_identity", "screen_sanctions")

MISSING_EXPIRY_RETRY = (
    "check_expiry reported the ID's expiry date missing, so the case cannot be approved. "
    "Request resubmission of the ID with a reason naming the missing expiry date, or escalate."
)


def missing_tool_calls(ctx: RunContext[AssessmentDeps]) -> list[str]:
    """The required tools with no `ToolReturnPart` yet. A call whose arguments failed
    validation leaves a retry prompt, not a return."""
    returned = {
        part.tool_name
        for message in ctx.messages
        for part in message.parts
        if isinstance(part, ToolReturnPart)
    }
    return [tool for tool in REQUIRED_TOOLS if tool not in returned]


def expiry_date_missing(ctx: RunContext[AssessmentDeps]) -> bool:
    """Whether a `check_expiry` call in this run returned `status="missing"`. In a workflow the
    result comes back from its activity as a dict, and one recorded before `status` existed has
    no status."""
    for message in ctx.messages:
        for part in message.parts:
            if not isinstance(part, ToolReturnPart) or part.tool_name != "check_expiry":
                continue
            content = part.content
            status = (
                content.get("status")
                if isinstance(content, dict)
                else getattr(content, "status", None)
            )
            if status == "missing":
                return True
    return False


def decision_from_answer(
    ctx: RunContext[AssessmentDeps],
    answer: AssessmentAnswer,
) -> ApproveDecision | RequestResubmissionDecision | EscalateDecision:
    """Turn the flat answer into the decision it names. The model is asked again when a
    required tool has not returned, the decision lacks a field, or it approves an ID whose
    expiry date is missing."""
    missing = missing_tool_calls(ctx)
    if missing:
        raise ModelRetry(
            "Before deciding, call the tools that have not returned a result yet: "
            f"{', '.join(missing)}."
        )
    try:
        decision = _DECISION_ADAPTER.validate_python(answer.model_dump(exclude_none=True))
    except ValidationError as error:
        raise ModelRetry(str(error)) from error
    if isinstance(decision, ApproveDecision) and expiry_date_missing(ctx):
        raise ModelRetry(MISSING_EXPIRY_RETRY)
    return decision


def build_assessment_agent(
    *,
    instructions: str,
    base_url: str,
    model_name: str,
    faults: FaultRegistry,
) -> Agent[AssessmentDeps, AssessmentDecision]:
    """Build the assessment agent, which approves, requests resubmission, or escalates after
    calling the three tools.

    The decision comes back as JSON in the text answer (`PromptedOutput`). `NativeOutput`
    sets a `response_format` under which Ollama never calls a tool, and an output tool is one
    qwen3.5:9B often skips. The flat `AssessmentAnswer` replaces Pydantic AI's nested envelope
    for a union, which the model often left a brace short. `instructions` is the loaded prompt
    text.
    """
    return Agent(
        build_ollama_model(base_url, model_name, faults, injects_bad_output=False),
        name="kyc-assessment",
        description=(
            "Checks a case's extracted documents for expiry, identity and sanctions, then "
            "approves, asks for resubmission or escalates to a reviewer."
        ),
        retries={"output": OUTPUT_RETRIES},
        deps_type=AssessmentDeps,
        output_type=PromptedOutput(
            decision_from_answer, name="assessment_decision", template=DECISION_SCHEMA_TEMPLATE
        ),
        instructions=instructions,
        tools=[check_expiry, compare_identity, screen_sanctions],
        capabilities=[
            TemporalDurability[AssessmentDeps](
                activity_config=TOOL_ACTIVITY_CONFIG,
                model_activity_config=MODEL_ACTIVITY_CONFIG,
            )
        ],
    )
