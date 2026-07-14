"""FastAPI entrypoint for the SRE runbook assistant.

Telemetry is set up (with the DB engine, so SQLAlchemy is instrumented) BEFORE
the app serves traffic. Each request is single-shot: a per-request UUID becomes
gen_ai.conversation.id, and the diagnosis is persisted with the current trace_id.
"""

import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from opentelemetry import trace
from pydantic import BaseModel

from runbook_assistant.agent import build_agent, run_diagnosis
from runbook_assistant.config import get_settings
from runbook_assistant.db import (
    init_db,
    make_engine,
    make_session_factory,
    save_diagnosis,
)
from runbook_assistant.telemetry.callback import OTelCallbackHandler
from runbook_assistant.telemetry.setup import instrument_fastapi, setup_telemetry
from runbook_assistant.tools import _services


class DiagnoseRequest(BaseModel):
    question: str


class DiagnoseResponse(BaseModel):
    answer: str
    diagnosis_id: str


def _detect_service(question: str) -> str | None:
    q = question.lower()
    return next((name for name in _services() if name in q), None)


def _current_trace_id() -> str | None:
    ctx = trace.get_current_span().get_span_context()
    return format(ctx.trace_id, "032x") if ctx.is_valid else None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    s = get_settings()
    engine = make_engine(s.database_url)
    setup_telemetry(engine=engine)
    await init_db(engine)
    app.state.session_factory = make_session_factory(engine)

    from runbook_assistant.retriever import build_retriever, seed_runbooks

    retriever, store = build_retriever(s.database_url.replace("+asyncpg", "+psycopg"))
    seed_runbooks(store)
    app.state.agent = build_agent(retriever)

    if s.instrumentation_mode == "callback":
        app.state.handler_factory = lambda conversation_id: [
            OTelCallbackHandler(
                agent_name="runbook_assistant",
                data_source_id=s.data_source_id,
                conversation_id=conversation_id,
            )
        ]
    else:
        app.state.handler_factory = lambda _conversation_id: []
    yield
    await engine.dispose()


def create_app() -> FastAPI:
    app = FastAPI(title="AI Runbook Assistant", lifespan=lifespan)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz")
    async def readyz() -> dict[str, str]:
        return {"status": "ready"}

    @app.post("/api/v1/diagnose", response_model=DiagnoseResponse)
    async def diagnose(req: DiagnoseRequest) -> DiagnoseResponse:
        conversation_id = str(uuid.uuid4())
        callbacks = app.state.handler_factory(conversation_id)
        start = time.perf_counter()
        answer = run_diagnosis(app.state.agent, req.question, callbacks)
        duration_ms = int((time.perf_counter() - start) * 1000)
        diagnosis_id = await save_diagnosis(
            app.state.session_factory,
            question=req.question,
            answer=answer,
            service=_detect_service(req.question),
            duration_ms=duration_ms,
            trace_id=_current_trace_id(),
        )
        return DiagnoseResponse(answer=answer, diagnosis_id=diagnosis_id)

    instrument_fastapi(app)
    return app


app = create_app()
