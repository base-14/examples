import asyncio
import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import cast

from fastapi import FastAPI, HTTPException, Request
from fastapi.exception_handlers import (
    http_exception_handler,
    request_validation_exception_handler,
)
from fastapi.exceptions import RequestValidationError
from opentelemetry import trace
from opentelemetry.util.types import AttributeValue
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response
from temporalio.client import (
    Client,
    WorkflowExecutionStatus,
    WorkflowUpdateFailedError,
)
from temporalio.exceptions import ApplicationError
from temporalio.service import RPCError, RPCStatusCode

from kyc_onboarding.agents import FaultRegistry, PostgresFaultRegistry
from kyc_onboarding.attributes import (
    ACCOUNT_TYPE_ATTRIBUTE,
    CASE_ID_ATTRIBUTE,
    DOCUMENT_TYPE_ATTRIBUTE,
    HTTP_STATUS_CODE_ATTRIBUTE,
    REVIEW_DECISION_ATTRIBUTE,
)
from kyc_onboarding.config import get_settings
from kyc_onboarding.models import (
    CaseCreateRequest,
    CaseInput,
    CaseStatus,
    CaseStatusView,
    DocumentAccepted,
    ReviewDecision,
    SubmittedDocument,
    required_documents_for,
)
from kyc_onboarding.telemetry import (
    configure_telemetry,
    create_temporal_client,
    instrument_fastapi_app,
    service_name,
)
from kyc_onboarding.workflows import CASE_NOT_IN_REVIEW_ERROR, KycOnboardingWorkflow


settings = get_settings()
logger = logging.getLogger(__name__)

FALLBACK_SERVICE_NAME = "ai-kyc-onboarding-api"
CASE_NOT_FOUND_DETAIL = "case not found"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_telemetry(FALLBACK_SERVICE_NAME)
    app.state.temporal_client = await create_temporal_client(settings)
    app.state.fault_registry = PostgresFaultRegistry(settings.kyc_db_dsn)
    yield


app = FastAPI(title="KYC Onboarding Agent", lifespan=lifespan)
instrument_fastapi_app(app)


@app.exception_handler(StarletteHTTPException)
async def log_refused_request(request: Request, error: StarletteHTTPException) -> Response:
    _log_refusal(request, error.status_code, str(error.detail))
    return await http_exception_handler(request, error)


@app.exception_handler(RequestValidationError)
async def log_invalid_request(request: Request, error: RequestValidationError) -> Response:
    _log_refusal(request, 422, "request body failed validation")
    return await request_validation_exception_handler(request, error)


def _log_refusal(request: Request, status_code: int, detail: str) -> None:
    attributes: dict[str, object] = {HTTP_STATUS_CODE_ATTRIBUTE: status_code}
    if "case_id" in request.path_params:
        attributes[CASE_ID_ATTRIBUTE] = request.path_params["case_id"]
        _set_span_attributes({CASE_ID_ATTRIBUTE: request.path_params["case_id"]})
    logger.warning(
        "request refused: %s %s returned %s, %s",
        request.method,
        request.url.path,
        status_code,
        detail,
        extra=attributes,
    )


def _set_span_attributes(attributes: dict[str, AttributeValue]) -> None:
    """Sets case attributes on the current span, the request's FastAPI server span."""
    trace.get_current_span().set_attributes(attributes)


def _temporal_client() -> Client:
    return cast("Client", app.state.temporal_client)


def _fault_registry() -> FaultRegistry:
    return cast("FaultRegistry", app.state.fault_registry)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "healthy", "service": service_name(FALLBACK_SERVICE_NAME)}


@app.post("/cases", status_code=201)
async def create_case(request: CaseCreateRequest) -> CaseStatusView:
    _set_span_attributes({ACCOUNT_TYPE_ATTRIBUTE: request.account_type.value})
    if request.has_fault_overrides and not settings.faults_enabled:
        raise HTTPException(
            status_code=422,
            detail="fault and deadline/budget overrides require KYC_FAULTS_ENABLED=true",
        )

    case_id = str(uuid.uuid4())
    _set_span_attributes({CASE_ID_ATTRIBUTE: case_id})
    document_deadline = (
        timedelta(seconds=request.document_deadline_seconds)
        if request.document_deadline_seconds is not None
        else timedelta(days=settings.document_deadline_days)
    )
    review_deadline = (
        timedelta(seconds=request.review_deadline_seconds)
        if request.review_deadline_seconds is not None
        else timedelta(days=settings.review_deadline_days)
    )
    case_input = CaseInput(
        case_id=case_id,
        name=request.name,
        country=request.country,
        account_type=request.account_type,
        document_deadline=document_deadline,
        review_deadline=review_deadline,
        request_budget=request.request_budget or settings.request_budget,
        extraction_prompt_version=settings.extraction_prompt_version,
        assessment_prompt_version=settings.assessment_prompt_version,
        fault=request.fault,
    )

    if request.fault is not None:
        await asyncio.to_thread(_fault_registry().record_fault, case_id, request.fault)

    await _temporal_client().start_workflow(
        KycOnboardingWorkflow.run,
        case_input,
        id=case_id,
        task_queue=settings.temporal_task_queue,
    )
    logger.info(
        "case created",
        extra={CASE_ID_ATTRIBUTE: case_id, ACCOUNT_TYPE_ATTRIBUTE: request.account_type.value},
    )

    return CaseStatusView(
        case_id=case_id,
        account_type=request.account_type,
        status=CaseStatus.awaiting_documents,
        missing_documents=list(required_documents_for(request.account_type)),
        resubmission_round=0,
        decisions=[],
        review=None,
        outcome=None,
        escalation_reason=None,
    )


@app.post("/cases/{case_id}/documents", status_code=202)
async def submit_document(case_id: str, document: SubmittedDocument) -> DocumentAccepted:
    _set_span_attributes(
        {CASE_ID_ATTRIBUTE: case_id, DOCUMENT_TYPE_ATTRIBUTE: document.document_type.value}
    )
    handle = _temporal_client().get_workflow_handle(case_id)
    try:
        description = await handle.describe()
    except RPCError as error:
        if error.status == RPCStatusCode.NOT_FOUND:
            raise HTTPException(status_code=404, detail=CASE_NOT_FOUND_DETAIL) from None
        raise
    if description.status != WorkflowExecutionStatus.RUNNING:
        raise HTTPException(status_code=409, detail="case is closed") from None

    await handle.signal(KycOnboardingWorkflow.submit_document, document)
    logger.info(
        "document accepted",
        extra={
            CASE_ID_ATTRIBUTE: case_id,
            DOCUMENT_TYPE_ATTRIBUTE: document.document_type.value,
        },
    )
    return DocumentAccepted(case_id=case_id, document_type=document.document_type)


@app.post("/cases/{case_id}/review")
async def submit_review(case_id: str, review: ReviewDecision) -> CaseStatusView:
    _set_span_attributes({CASE_ID_ATTRIBUTE: case_id, REVIEW_DECISION_ATTRIBUTE: review.decision})
    handle = _temporal_client().get_workflow_handle(case_id)
    try:
        view = await handle.execute_update(KycOnboardingWorkflow.submit_review, review)
    except WorkflowUpdateFailedError as error:
        if (
            isinstance(error.cause, ApplicationError)
            and error.cause.type == CASE_NOT_IN_REVIEW_ERROR
        ):
            raise HTTPException(status_code=409, detail=error.cause.message) from None
        raise
    except RPCError as error:
        if error.status == RPCStatusCode.NOT_FOUND:
            raise HTTPException(status_code=404, detail=CASE_NOT_FOUND_DETAIL) from None
        raise
    logger.info(
        "review accepted",
        extra={CASE_ID_ATTRIBUTE: case_id, REVIEW_DECISION_ATTRIBUTE: review.decision},
    )
    return view


@app.get("/cases/{case_id}")
async def get_case(case_id: str) -> CaseStatusView:
    _set_span_attributes({CASE_ID_ATTRIBUTE: case_id})
    handle = _temporal_client().get_workflow_handle(case_id)
    try:
        return await handle.query(KycOnboardingWorkflow.status)
    except RPCError as error:
        if error.status == RPCStatusCode.NOT_FOUND:
            raise HTTPException(status_code=404, detail=CASE_NOT_FOUND_DETAIL) from None
        raise
