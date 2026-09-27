"""The analyst's typed answer, returned through Strands' structured output tool."""

from typing import Literal

from pydantic import BaseModel, Field


ACCESSION_PATTERN = r"^\d{10}-\d{2}-\d{6}$"

type RatioName = Literal[
    "net_margin",
    "operating_margin",
    "gross_margin",
    "revenue_growth",
    "current_ratio",
    "liabilities_to_assets",
]


class Figure(BaseModel):
    """One figure used in the answer, exactly as a tool returned it."""

    concept: str = Field(description="The concept or tag the tool returned.")
    value: float = Field(description="The value exactly as the tool returned it, not rounded.")
    unit: str = Field(description="The unit, such as USD or USD/shares.")
    fiscal_year: int = Field(description="The fiscal year the tool returned.")
    form: str = Field(description="The filing form, such as 10-K.")
    accession: str = Field(
        pattern=ACCESSION_PATTERN, description="The accession number the tool returned."
    )


class RatioUsed(BaseModel):
    """One ratio used in the answer, as compute_ratio returned it."""

    name: RatioName = Field(description="The ratio name compute_ratio was called with.")
    value: float = Field(
        description="The ratio as a decimal fraction, as compute_ratio returned it."
    )
    fiscal_year: int
    accessions: list[str] = Field(description="Both accession numbers compute_ratio returned.")


class FilingAnswer(BaseModel):
    """The answer to the question, with every figure and ratio it uses."""

    answer: str = Field(description="A short answer in plain sentences.")
    figures: list[Figure] = Field(description="Every figure the answer uses, or empty.")
    ratios: list[RatioUsed] = Field(default_factory=list, description="Every ratio used.")
    caveats: list[str] = Field(
        default_factory=list, description="What the data does not cover, or what was searched."
    )
