"""Rows parsed from an SEC company facts document."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Literal


KEPT_TAXONOMIES = ("us-gaap", "dei")
KEPT_UNITS = frozenset({"USD", "shares", "pure", "USD/shares"})

type FactSource = Literal["cache", "sec"]


@dataclass(frozen=True)
class FactRow:
    """One reported value. `filing_fy` and `filing_fp` are the filing's fiscal year and period
    as the SEC reports them, not the fact's: a 10-K repeats the two prior years under its own
    `fy`. The fiscal year served to the model comes from `period_end`."""

    taxonomy: str
    concept: str
    unit: str
    period_start: date | None
    period_end: date
    value: Decimal
    filing_fy: int | None
    filing_fp: str | None
    form: str
    filed: date
    accession: str
    frame: str | None

    @property
    def key(self) -> tuple[str, str, str, date | None, date, str]:
        return (
            self.taxonomy,
            self.concept,
            self.unit,
            self.period_start,
            self.period_end,
            self.accession,
        )


def _row(taxonomy: str, concept: str, unit: str, fact: dict[str, Any]) -> FactRow:
    start = fact.get("start")
    return FactRow(
        taxonomy=taxonomy,
        concept=concept,
        unit=unit,
        period_start=date.fromisoformat(start) if start else None,
        period_end=date.fromisoformat(fact["end"]),
        value=Decimal(str(fact["val"])),
        filing_fy=fact.get("fy"),
        filing_fp=fact.get("fp"),
        form=fact["form"],
        filed=date.fromisoformat(fact["filed"]),
        accession=fact["accn"],
        frame=fact.get("frame"),
    )


def parse_company_facts(document: dict[str, Any]) -> list[FactRow]:
    """Keep us-gaap and dei facts in the four units the tools read, one row per concept, unit,
    start, end and accession number. The SEC lists a fact twice in one filing when it carries a
    frame; the row with the frame is kept."""
    rows: dict[tuple[str, str, str, date | None, date, str], FactRow] = {}
    facts = document.get("facts", {})
    for taxonomy in KEPT_TAXONOMIES:
        for concept, body in facts.get(taxonomy, {}).items():
            for unit, entries in body.get("units", {}).items():
                if unit not in KEPT_UNITS:
                    continue
                for entry in entries:
                    row = _row(taxonomy, concept, unit, entry)
                    if row.key not in rows or row.frame is not None:
                        rows[row.key] = row
    return list(rows.values())
