"""Shared scaffolding for the workflow tests: scripted models, case input and a test worker.

The scripted models run in activities on the host, so they can keep state across calls.
"""

import asyncio
import contextlib
import json
import logging
import re
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any
from unittest.mock import patch

from pydantic import BaseModel
from pydantic_ai.durable_exec.temporal import PydanticAIPlugin
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models import Model
from pydantic_ai.models.function import AgentInfo, FunctionModel
from temporalio.client import Client, WorkflowHandle
from temporalio.contrib.opentelemetry import OpenTelemetryPlugin
from temporalio.testing import WorkflowEnvironment

from kyc_onboarding.agents import (
    FaultInjectingModel,
    FaultRegistry,
    StaticFaultRegistry,
    build_assessment_agent,
    build_extraction_agent,
    load_prompt,
)
from kyc_onboarding.agents.assessment import REQUIRED_TOOLS
from kyc_onboarding.case_agents import CaseAgents
from kyc_onboarding.models import (
    AccountType,
    ApproveDecision,
    AssessmentDecision,
    CaseFault,
    CaseInput,
    CaseStatus,
    CaseStatusView,
    DocumentType,
    ExtractedIdFields,
    ExtractedProofOfAddressFields,
    ExtractedRegistrationCertificateFields,
    SubmittedDocument,
)
from kyc_onboarding.workflows import KycOnboardingWorkflow
from tests._telemetry_support import (
    global_logger_provider,
    global_metric_reader,
    global_tracer_provider,
)


APPLICANT = "Maria Gonzalez"
DOCUMENT_DEADLINE = timedelta(days=7)
REVIEW_DEADLINE = timedelta(days=3)
REQUEST_BUDGET = 40
EXTRACTION_PROMPT_VERSION = "v1"
ASSESSMENT_PROMPT_VERSION = "v3"
VALID_EXPIRY_DATE = "2099-12-31"

ModelFunction = Callable[[list[ModelMessage], AgentInfo], ModelResponse]

_EXTRACTED_FIELDS: dict[DocumentType, BaseModel] = {
    DocumentType.id: ExtractedIdFields(
        full_name=APPLICANT, date_of_birth=date(1988, 4, 12), id_number="NIC-778241"
    ),
    DocumentType.proof_of_address: ExtractedProofOfAddressFields(
        account_holder=APPLICANT, address="14 Harbour Road, Cork"
    ),
    DocumentType.registration_certificate: ExtractedRegistrationCertificateFields(
        company_name="Gonzalez Trading Ltd",
        registration_number="IE-554120",
        address="14 Harbour Road, Cork",
        authorized_representative=APPLICANT,
    ),
}


def case_input(
    case_id: str,
    *,
    account_type: AccountType = AccountType.personal,
    fault: CaseFault | None = None,
    request_budget: int = REQUEST_BUDGET,
) -> CaseInput:
    return CaseInput(
        case_id=case_id,
        name=APPLICANT,
        country="IE",
        account_type=account_type,
        document_deadline=DOCUMENT_DEADLINE,
        review_deadline=REVIEW_DEADLINE,
        request_budget=request_budget,
        extraction_prompt_version=EXTRACTION_PROMPT_VERSION,
        assessment_prompt_version=ASSESSMENT_PROMPT_VERSION,
        fault=fault,
    )


def document(document_type: DocumentType) -> SubmittedDocument:
    return SubmittedDocument(
        document_type=document_type, raw_text=f"{document_type} for {APPLICANT}"
    )


def required_documents(account_type: AccountType = AccountType.personal) -> list[SubmittedDocument]:
    types = [DocumentType.id, DocumentType.proof_of_address]
    if account_type == AccountType.business:
        types.append(DocumentType.registration_certificate)
    return [document(document_type) for document_type in types]


def _user_prompt(messages: list[ModelMessage]) -> str:
    return "\n".join(
        str(part.content)
        for message in messages
        if isinstance(message, ModelRequest)
        for part in message.parts
        if isinstance(part, UserPromptPart)
    )


def _output_call(info: AgentInfo, output: BaseModel) -> ModelResponse:
    tool_name = f"final_result_{type(output).__name__}"
    assert tool_name in {tool.name for tool in info.output_tools}, tool_name
    return ModelResponse(
        parts=[ToolCallPart(tool_name=tool_name, args=output.model_dump(mode="json"))]
    )


def check_calls(*calls: ToolCallPart) -> ModelResponse:
    """Calls every required tool; each call in `calls` replaces its default and goes last."""
    given = {call.tool_name for call in calls}
    defaults = [
        ToolCallPart(tool_name="check_expiry", args={"expiry_date": VALID_EXPIRY_DATE}),
        ToolCallPart(tool_name="compare_identity", args={}),
        ToolCallPart(tool_name="screen_sanctions", args={"name": APPLICANT}),
    ]
    return ModelResponse(parts=[c for c in defaults if c.tool_name not in given] + list(calls))


def checks_done(messages: list[ModelMessage]) -> bool:
    returned = {
        part.tool_name
        for message in messages
        for part in getattr(message, "parts", ())
        if isinstance(part, ToolReturnPart)
    }
    return set(REQUIRED_TOOLS) <= returned


def decision_answer(decision: AssessmentDecision) -> ModelResponse:
    """The decision as one flat JSON object in text, the shape of `AssessmentAnswer`."""
    return ModelResponse(parts=[TextPart(content=json.dumps(decision.model_dump(mode="json")))])


@dataclass
class ScriptedExtraction:
    """Returns the fields for whichever document type the extraction prompt names."""

    calls: list[DocumentType] = field(default_factory=list)
    fields_override: Mapping[DocumentType, BaseModel] = field(default_factory=dict)

    def __call__(self, messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        match = re.search(r"Document type: (\w+)", _user_prompt(messages))
        assert match is not None
        document_type = DocumentType(match.group(1))
        self.calls.append(document_type)
        fields = self.fields_override.get(document_type, _EXTRACTED_FIELDS[document_type])
        return _output_call(info, fields)


@dataclass
class ScriptedAssessment:
    """Calls every required tool, then returns the next decision, one per answer. `checks`
    replaces the default tool calls, as in `check_calls`."""

    decisions: Sequence[AssessmentDecision] = (ApproveDecision(),)
    checks: Sequence[ToolCallPart] = ()
    rounds: int = 0

    def __call__(self, messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if not checks_done(messages):
            return check_calls(*self.checks)
        decision = self.decisions[min(self.rounds, len(self.decisions) - 1)]
        self.rounds += 1
        return decision_answer(decision)


def build_test_agents(
    extraction: ModelFunction,
    assessment: ModelFunction,
    faults: FaultRegistry | None = None,
) -> CaseAgents:
    """Both agents from the real builders, each on a fault-injecting scripted model."""
    scripted = {"scripted-extraction": extraction, "scripted-assessment": assessment}

    def scripted_model(
        base_url: str,
        model_name: str,
        registry: FaultRegistry,
        *,
        injects_bad_output: bool = True,
    ) -> Model:
        return FaultInjectingModel(
            FunctionModel(scripted[model_name], model_name=model_name),
            faults=registry,
            injects_bad_output=injects_bad_output,
        )

    registry = faults or StaticFaultRegistry()
    extraction_prompt = load_prompt(f"extraction_{EXTRACTION_PROMPT_VERSION}")
    assessment_prompt = load_prompt(f"assessment_{ASSESSMENT_PROMPT_VERSION}")
    with (
        patch("kyc_onboarding.agents.extraction.build_ollama_model", scripted_model),
        patch("kyc_onboarding.agents.assessment.build_ollama_model", scripted_model),
    ):
        return CaseAgents(
            extraction=build_extraction_agent(
                instructions=extraction_prompt.system,
                base_url="unused",
                model_name="scripted-extraction",
                faults=registry,
            ),
            assessment=build_assessment_agent(
                instructions=assessment_prompt.system,
                base_url="unused",
                model_name="scripted-assessment",
                faults=registry,
            ),
            extraction_prompt=extraction_prompt,
            assessment_prompt=assessment_prompt,
            extraction_prompt_version=EXTRACTION_PROMPT_VERSION,
            assessment_prompt_version=ASSESSMENT_PROMPT_VERSION,
            sanctions_dsn="postgresql://stub/kyc",
        )


def client_plugins() -> list[Any]:
    return [PydanticAIPlugin(), OpenTelemetryPlugin(add_temporal_spans=True)]


@asynccontextmanager
async def time_skipping_env() -> Any:
    global_tracer_provider()
    global_metric_reader()
    global_logger_provider()
    async with await WorkflowEnvironment.start_time_skipping(plugins=client_plugins()) as env:
        yield env


async def start_case(
    client: Client, task_queue: str, case: CaseInput
) -> WorkflowHandle[KycOnboardingWorkflow, CaseStatusView]:
    return await client.start_workflow(
        KycOnboardingWorkflow.run, case, id=case.case_id, task_queue=task_queue
    )


async def send_documents(
    handle: WorkflowHandle[KycOnboardingWorkflow, CaseStatusView],
    documents: Sequence[SubmittedDocument],
) -> None:
    for submitted in documents:
        await handle.signal(KycOnboardingWorkflow.submit_document, submitted)


async def wait_until(
    handle: WorkflowHandle[KycOnboardingWorkflow, CaseStatusView],
    reached: Callable[[CaseStatusView], bool],
    *,
    timeout: float = 10.0,
) -> CaseStatusView:
    async with asyncio.timeout(timeout):
        while True:
            view = await handle.query(KycOnboardingWorkflow.status)
            if reached(view):
                return view
            await asyncio.sleep(0.05)


async def wait_for_status(
    handle: WorkflowHandle[KycOnboardingWorkflow, CaseStatusView],
    status: CaseStatus,
    *,
    resubmission_round: int = 0,
) -> CaseStatusView:
    return await wait_until(
        handle,
        lambda view: view.status == status and view.resubmission_round == resubmission_round,
    )


async def final_attempts(
    handle: WorkflowHandle[KycOnboardingWorkflow, CaseStatusView],
) -> list[tuple[str, int]]:
    """Each activity type the case ran, with the attempt that completed it."""
    events = (await handle.fetch_history()).events
    names = {
        event.event_id: event.activity_task_scheduled_event_attributes.activity_type.name
        for event in events
        if event.HasField("activity_task_scheduled_event_attributes")
    }
    return [
        (
            names[event.activity_task_started_event_attributes.scheduled_event_id],
            event.activity_task_started_event_attributes.attempt,
        )
        for event in events
        if event.HasField("activity_task_started_event_attributes")
    ]


class WorkflowTaskFailures(logging.Handler):
    """Collects workflow task failure messages the worker logs."""

    def __init__(self) -> None:
        super().__init__()
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        if record.exc_info and record.exc_info[1] is not None:
            self.messages.append(str(record.exc_info[1]))

    async def first(self, *, timeout: float = 10.0) -> str:
        async with asyncio.timeout(timeout):
            while not self.messages:
                await asyncio.sleep(0.05)
        return self.messages[0]


@contextlib.contextmanager
def workflow_task_failures() -> Iterator[WorkflowTaskFailures]:
    handler = WorkflowTaskFailures()
    temporal_logger = logging.getLogger("temporalio")
    temporal_logger.addHandler(handler)
    try:
        yield handler
    finally:
        temporal_logger.removeHandler(handler)
