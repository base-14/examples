from typing import Literal

from pydantic import BaseModel, Field


class ContentIssue(BaseModel):
    type: Literal["hyperbole", "bias", "unsourced", "unclear", "grammar", "other"] = Field(
        description="Category of the quality issue identified"
    )
    description: str = Field(description="Specific explanation of the issue")
    location: str | None = Field(default=None, description="Quote of the problematic text")
    severity: Literal["low", "medium", "high"] = Field(
        description="Impact: low=style, medium=credibility, high=factual"
    )


class ReviewResult(BaseModel):
    issues: list[ContentIssue] = Field(
        default_factory=list, description="List of quality issues found in the content"
    )
    summary: str = Field(description="Brief overview of the content quality assessment")
    overall_quality: Literal["poor", "fair", "good", "excellent"] = Field(
        description="Overall quality rating of the content"
    )


class ImprovementSuggestion(BaseModel):
    original: str = Field(description="The original text that needs improvement")
    improved: str = Field(description="The suggested improved version of the text")
    reason: str = Field(description="Explanation of why this change improves the content")


class ImproveResult(BaseModel):
    suggestions: list[ImprovementSuggestion] = Field(
        default_factory=list, description="List of specific improvement suggestions"
    )
    summary: str = Field(description="Brief overview of suggested improvements")


class ScoreBreakdown(BaseModel):
    clarity: int = Field(ge=0, le=100, description="How clear and understandable the content is")
    accuracy: int = Field(ge=0, le=100, description="How factually accurate the content is")
    engagement: int = Field(ge=0, le=100, description="How engaging and compelling the content is")
    originality: int = Field(ge=0, le=100, description="How original and unique the content is")


class ScoreResult(BaseModel):
    score: int = Field(ge=0, le=100, description="Overall content quality score")
    breakdown: ScoreBreakdown = Field(description="Detailed score breakdown by category")
    summary: str = Field(description="Brief explanation of the scoring rationale")
