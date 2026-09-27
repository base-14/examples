import json
from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from filing_analyst.facts import FactRow, parse_company_facts
from filing_analyst.fixtures import FactsCache


TEST_FIXTURES = Path(__file__).parent / "fixtures"
CACHE = FactsCache(Path(__file__).parents[1] / "fixtures")
WORKIVA = 1445305
RINGCENTRAL = 1384905
AIRBNB = 1559720
GITLAB = 1653482
MONDAY = 1845338
AMPLITUDE = 1866692


def recorded(cik: int) -> dict[str, Any]:
    path = TEST_FIXTURES / "companyfacts" / f"CIK{cik:010d}.json"
    if path.exists():
        document: dict[str, Any] = json.loads(path.read_text())
        return document
    cached = CACHE.read(cik)
    assert cached is not None
    return cached


class MemoryFacts:
    def __init__(self, rows_by_cik: dict[int, list[FactRow]]) -> None:
        self._rows = rows_by_cik

    @classmethod
    def of(cls, *ciks: int) -> MemoryFacts:
        return cls({cik: parse_company_facts(recorded(cik)) for cik in ciks})

    def facts(self, cik: int, taxonomy: str, concepts: Sequence[str]) -> list[FactRow]:
        return [
            row
            for row in self._rows.get(cik, [])
            if row.taxonomy == taxonomy and row.concept in concepts
        ]


def fact(
    concept: str,
    value: int,
    *,
    start: date | None,
    end: date,
    form: str = "10-K",
    filed: date,
    accession: str,
) -> FactRow:
    return FactRow(
        taxonomy="us-gaap",
        concept=concept,
        unit="USD",
        period_start=start,
        period_end=end,
        value=Decimal(value),
        filing_fy=end.year,
        filing_fp="FY",
        form=form,
        filed=filed,
        accession=accession,
        frame=None,
    )
