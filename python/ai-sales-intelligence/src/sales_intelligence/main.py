"""FastAPI application for AI Sales Intelligence."""

import csv
import io
import logging
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Annotated, Any

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sales_intelligence.config import get_settings
from sales_intelligence.database import close_db, engine, get_session, init_db
from sales_intelligence.graph import run_pipeline
from sales_intelligence.middleware import MetricsMiddleware
from sales_intelligence.models import Campaign, Connection, Prospect
from sales_intelligence.telemetry import instrument_fastapi, setup_telemetry


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
settings = get_settings()

tracer, meter = setup_telemetry(engine)


@asynccontextmanager
async def lifespan(app: FastAPI) -> Any:
    """Application lifespan manager."""
    await init_db()
    logger.info("Database initialized")
    yield
    await close_db()
    logger.info("Database connections closed")


app = FastAPI(
    title="AI Sales Intelligence",
    description="AI-powered sales prospecting and outreach automation",
    version="2.0.0",
    lifespan=lifespan,
)
app.add_middleware(MetricsMiddleware)
instrument_fastapi(app)

SessionDep = Annotated[AsyncSession, Depends(get_session)]


class CampaignCreate(BaseModel):
    """Request to create a campaign."""

    name: str
    target_keywords: list[str] = Field(default_factory=list)
    target_titles: list[str] = Field(default_factory=list)


class CampaignResponse(BaseModel):
    """Campaign response model."""

    id: str
    name: str
    target_keywords: list[str]
    target_titles: list[str]
    status: str
    created_at: datetime


class PipelineRequest(BaseModel):
    """Request to run the pipeline."""

    score_threshold: int = Field(default=50, ge=0, le=100)
    quality_threshold: int = Field(default=60, ge=0, le=100)


class PipelineResponse(BaseModel):
    """Pipeline execution result."""

    campaign_id: str
    prospects_found: int
    prospects_scored: int
    drafts_generated: int
    drafts_passed: int
    errors: list[str]


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    service: str
    version: str


@app.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Health check endpoint."""
    return HealthResponse(
        status="healthy",
        service=settings.app_name,
        version="2.0.0",
    )


@app.post("/campaigns", response_model=CampaignResponse)
async def create_campaign(request: CampaignCreate, session: SessionDep) -> CampaignResponse:
    """Create a new campaign."""
    campaign = Campaign(
        name=request.name,
        target_keywords=",".join(request.target_keywords),
        target_titles=",".join(request.target_titles),
        status="draft",
    )
    session.add(campaign)
    await session.flush()

    return CampaignResponse(
        id=str(campaign.id),
        name=campaign.name,
        target_keywords=request.target_keywords,
        target_titles=request.target_titles,
        status=campaign.status,
        created_at=campaign.created_at,
    )


@app.get("/campaigns/{campaign_id}", response_model=CampaignResponse)
async def get_campaign(campaign_id: str, session: SessionDep) -> CampaignResponse:
    """Get a campaign by ID."""
    try:
        uid = uuid.UUID(campaign_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid campaign ID") from e

    result = await session.execute(select(Campaign).where(Campaign.id == uid))
    campaign = result.scalar_one_or_none()

    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    keywords = campaign.target_keywords.split(",") if campaign.target_keywords else []
    titles = campaign.target_titles.split(",") if campaign.target_titles else []

    return CampaignResponse(
        id=str(campaign.id),
        name=campaign.name,
        target_keywords=keywords,
        target_titles=titles,
        status=campaign.status,
        created_at=campaign.created_at,
    )


@app.post("/connections/import")
async def import_connections(
    file: Annotated[UploadFile, File(description="LinkedIn connections CSV")],
    session: SessionDep,
) -> dict[str, int]:
    """Import LinkedIn connections from CSV."""
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="File must be a CSV")

    content = await file.read()
    text = content.decode("utf-8")
    reader = csv.DictReader(io.StringIO(text))

    count = 0
    for row in reader:
        connection = Connection(
            first_name=row.get("First Name", ""),
            last_name=row.get("Last Name", ""),
            email=row.get("Email Address"),
            company=row.get("Company"),
            position=row.get("Position"),
        )
        session.add(connection)
        count += 1

    await session.flush()
    logger.info("Imported %d connections", count)

    return {"imported": count}


@app.post("/campaigns/{campaign_id}/run", response_model=PipelineResponse)
async def run_campaign(
    campaign_id: str,
    request: PipelineRequest,
    session: SessionDep,
) -> PipelineResponse:
    """Run the sales intelligence pipeline for a campaign."""
    try:
        uid = uuid.UUID(campaign_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid campaign ID") from e

    result = await session.execute(select(Campaign).where(Campaign.id == uid))
    campaign = result.scalar_one_or_none()

    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    keywords = campaign.target_keywords.split(",") if campaign.target_keywords else []
    titles = campaign.target_titles.split(",") if campaign.target_titles else []

    campaign.status = "running"
    await session.flush()

    state = await run_pipeline(
        campaign_id=campaign_id,
        target_keywords=keywords,
        target_titles=titles,
        session=session,
        score_threshold=request.score_threshold,
        quality_threshold=request.quality_threshold,
    )

    for scored in state.scored:
        draft = next(
            (d for d in state.drafts if d.prospect_id == scored.prospect.connection_id), None
        )
        evaluation = next(
            (e for e in state.evaluations if e.draft_id == scored.prospect.connection_id), None
        )

        prospect = Prospect(
            campaign_id=uid,
            connection_id=uuid.UUID(scored.prospect.connection_id),
            enrichment=scored.enrichment.model_dump(),
            icp_score=scored.icp_score,
            score_reasoning=scored.reasoning,
            email_subject=draft.subject if draft else None,
            email_body=draft.body if draft else None,
            quality_score=evaluation.quality_score if evaluation else None,
            quality_passed=evaluation.passed if evaluation else None,
        )
        session.add(prospect)

    campaign.status = "completed"
    await session.flush()

    return PipelineResponse(
        campaign_id=campaign_id,
        prospects_found=len(state.prospects),
        prospects_scored=len(state.scored),
        drafts_generated=len(state.drafts),
        drafts_passed=sum(1 for e in state.evaluations if e.passed),
        errors=state.errors,
    )


@app.get("/campaigns/{campaign_id}/prospects")
async def get_prospects(campaign_id: str, session: SessionDep) -> list[dict[str, Any]]:
    """Get prospects for a campaign."""
    try:
        uid = uuid.UUID(campaign_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid campaign ID") from e

    result = await session.execute(select(Prospect).where(Prospect.campaign_id == uid))
    prospects = result.scalars().all()

    return [
        {
            "id": str(p.id),
            "connection_id": str(p.connection_id),
            "icp_score": p.icp_score,
            "score_reasoning": p.score_reasoning,
            "email_subject": p.email_subject,
            "email_body": p.email_body,
            "quality_score": p.quality_score,
            "quality_passed": p.quality_passed,
            "enrichment": p.enrichment,
        }
        for p in prospects
    ]
