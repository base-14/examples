from typing import Literal

from pydantic import BaseModel, Field


class ContentRequest(BaseModel):
    content: str = Field(
        ...,
        min_length=1,
        max_length=10_000,
        description="Content to analyze (max 10,000 characters)",
    )
    content_type: Literal["marketing", "technical", "blog", "general"] = Field(
        default="general",
        description="Content category for eval attribution",
    )
