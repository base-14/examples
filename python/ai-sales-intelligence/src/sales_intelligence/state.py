"""LangGraph state models using Pydantic."""

from pydantic import BaseModel, Field


class ProspectData(BaseModel):
    """Prospect data from connection."""

    connection_id: str
    first_name: str
    last_name: str
    company: str
    position: str
    email: str | None = None


class EnrichedData(BaseModel):
    """Enriched company and prospect data from LLM."""

    industry: str | None = None
    company_size: str | None = None
    tech_stack: list[str] = Field(default_factory=list)
    recent_news: str | None = None
    pain_points: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class ScoredProspect(BaseModel):
    """Prospect with ICP score."""

    prospect: ProspectData
    enrichment: EnrichedData
    icp_score: int = Field(ge=0, le=100)
    reasoning: str


class EmailDraft(BaseModel):
    """Generated email draft."""

    prospect_id: str
    subject: str
    body: str


class EvaluationResult(BaseModel):
    """Quality evaluation result."""

    draft_id: str
    quality_score: int = Field(ge=0, le=100)
    passed: bool
    feedback: str
    issues: list[str] = Field(default_factory=list)


class AgentState(BaseModel):
    """State passed through LangGraph pipeline.

    This state flows through all agent nodes:
    research -> enrich -> score -> write -> evaluate
    """

    # Campaign context
    campaign_id: str
    target_keywords: list[str] = Field(default_factory=list)
    target_titles: list[str] = Field(default_factory=list)

    # Pipeline data
    prospects: list[ProspectData] = Field(default_factory=list)
    enriched: list[EnrichedData] = Field(default_factory=list)
    scored: list[ScoredProspect] = Field(default_factory=list)
    drafts: list[EmailDraft] = Field(default_factory=list)
    evaluations: list[EvaluationResult] = Field(default_factory=list)

    # Tracking
    errors: list[str] = Field(default_factory=list)
    current_step: str = "research"

    # Thresholds
    score_threshold: int = Field(default=50)
    quality_threshold: int = Field(default=60)
