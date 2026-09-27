"""The agents' tools: plain functions over stored facts and the SEC frames API, and the
Strands tools that bind them to one request's company."""

import logging
import statistics
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Protocol

from strands import tool
from strands.tools.decorator import DecoratedFunctionTool

from filing_analyst.concepts import ALIASES, ArgumentError, Concept, check_year, resolve_concept


if TYPE_CHECKING:
    from filing_analyst.facts import FactRow
    from filing_analyst.sec_client import SecClient


MAX_ROWS = 12
ANNUAL_FORMS = frozenset({"10-K", "10-K/A"})
ANNUAL_DAYS = range(330, 401)
LARGEST_SHOWN = 5
EARLY_JANUARY_LAST_DAY = 7

logger = logging.getLogger(__name__)


class FactReader(Protocol):
    def facts(self, cik: int, taxonomy: str, concepts: Sequence[str]) -> list[FactRow]: ...


def fiscal_year_of(period_end: date) -> int:
    """The calendar year the period ends in. A 52 or 53 week year that ends in the first days
    of January belongs to the year before."""
    if period_end.month == 1 and period_end.day <= EARLY_JANUARY_LAST_DAY:
        return period_end.year - 1
    return period_end.year


def _number(value: Decimal) -> int | float:
    return int(value) if value == value.to_integral_value() else float(value)


def _served(row: FactRow) -> dict[str, Any]:
    return {
        "concept": row.concept,
        "value": _number(row.value),
        "unit": row.unit,
        "period_start": row.period_start.isoformat() if row.period_start else None,
        "period_end": row.period_end.isoformat(),
        "fiscal_year": fiscal_year_of(row.period_end),
        "form": row.form,
        "accession": row.accession,
        "filed": row.filed.isoformat(),
    }


def _is_annual(row: FactRow, concept: Concept) -> bool:
    if row.form not in ANNUAL_FORMS or (concept.unit and row.unit != concept.unit):
        return False
    if row.period_start is None:
        return concept.instant is not False
    return concept.instant is not True and (row.period_end - row.period_start).days in ANNUAL_DAYS


def annual_facts(reader: FactReader, cik: int, concept: Concept) -> list[dict[str, Any]]:
    """One row per period, newest first. Where tags overlap the alias's first tag wins; within a
    tag the latest filed wins, as in the SEC's frames."""
    priority = {tag: index for index, tag in enumerate(concept.tags)}
    chosen: dict[tuple[date | None, date], FactRow] = {}
    for row in reader.facts(cik, concept.taxonomy, concept.tags):
        if not _is_annual(row, concept):
            continue
        period = (row.period_start, row.period_end)
        current = chosen.get(period)
        if current is None or (-priority[row.concept], row.filed, row.accession) > (
            -priority[current.concept],
            current.filed,
            current.accession,
        ):
            chosen[period] = row
    rows = sorted(chosen.values(), key=lambda r: r.period_end, reverse=True)
    return [_served(row) for row in rows]


def query_facts(
    reader: FactReader,
    cik: int,
    concept: str,
    fiscal_year_from: int | None = None,
    fiscal_year_to: int | None = None,
) -> dict[str, Any]:
    try:
        resolved = resolve_concept(concept)
        check_year(fiscal_year_from)
        check_year(fiscal_year_to)
        if fiscal_year_from and fiscal_year_to and fiscal_year_from > fiscal_year_to:
            raise ArgumentError("invalid_year", "fiscal_year_from is after fiscal_year_to.")
    except ArgumentError as error:
        return error.as_result()
    rows = [
        row
        for row in annual_facts(reader, cik, resolved)
        if (fiscal_year_from is None or row["fiscal_year"] >= fiscal_year_from)
        and (fiscal_year_to is None or row["fiscal_year"] <= fiscal_year_to)
    ]
    result: dict[str, Any] = {"concept": resolved.name, "rows": rows[:MAX_ROWS]}
    result["total_rows"] = len(rows)
    if not rows:
        logger.warning("Concept %s resolved to no 10-K facts for CIK %d", resolved.name, cik)
        result["note"] = (
            f"No annual 10-K facts for {resolved.name} (tags searched: "
            f"{', '.join(resolved.tags)}) in the requested years."
        )
    elif len(rows) > MAX_ROWS:
        result["note"] = f"Showing the latest {MAX_ROWS} of {len(rows)} fiscal years."
    return result


@dataclass(frozen=True)
class Ratio:
    numerator: str
    denominator: str
    prior_year_denominator: bool = False


RATIOS: dict[str, Ratio] = {
    "net_margin": Ratio("net_income", "revenue"),
    "operating_margin": Ratio("operating_income", "revenue"),
    "gross_margin": Ratio("gross_profit", "revenue"),
    "revenue_growth": Ratio("revenue", "revenue", prior_year_denominator=True),
    "current_ratio": Ratio("current_assets", "current_liabilities"),
    "liabilities_to_assets": Ratio("total_liabilities", "total_assets"),
}


def _by_year(reader: FactReader, cik: int, alias: str) -> dict[int, dict[str, Any]]:
    rows: dict[int, dict[str, Any]] = {}
    for row in annual_facts(reader, cik, ALIASES[alias]):
        rows.setdefault(row["fiscal_year"], row)
    return rows


def _missing(alias: str, fiscal_year: int | None) -> dict[str, Any]:
    when = f" for fiscal {fiscal_year}" if fiscal_year else ""
    return {
        "error": "missing_concept",
        "missing": alias,
        "detail": f"No 10-K value for {alias}{when}.",
    }


def compute_ratio(
    reader: FactReader, cik: int, ratio: str, fiscal_year: int | None = None
) -> dict[str, Any]:
    spec = RATIOS.get(ratio.strip().lower())
    if spec is None:
        return {"error": "unknown_ratio", "detail": f"Known ratios: {', '.join(RATIOS)}."}
    try:
        check_year(fiscal_year)
    except ArgumentError as error:
        return error.as_result()
    offset = 1 if spec.prior_year_denominator else 0
    numerators = _by_year(reader, cik, spec.numerator)
    denominators = _by_year(reader, cik, spec.denominator)
    if fiscal_year is None:
        years = [y for y in sorted(numerators, reverse=True) if y - offset in denominators]
        if not years:
            missing = spec.numerator if not numerators else spec.denominator
            return _missing(missing, None)
        fiscal_year = years[0]
    numerator = numerators.get(fiscal_year)
    if numerator is None:
        return _missing(spec.numerator, fiscal_year)
    denominator = denominators.get(fiscal_year - offset)
    if denominator is None or denominator["value"] == 0:
        return _missing(spec.denominator, fiscal_year - offset)
    value = Decimal(str(numerator["value"])) / Decimal(str(denominator["value"])) - offset
    return {
        "ratio": ratio,
        "fiscal_year": fiscal_year,
        "value": round(float(value), 4),
        "numerator": numerator,
        "denominator": denominator,
        "accessions": [numerator["accession"], denominator["accession"]],
    }


def frame_values(sec: SecClient, cik: int, concept: str, year: int) -> dict[str, Any]:
    """Transport failures raise, so the tool span records them."""
    try:
        resolved = resolve_concept(concept)
        check_year(year)
    except ArgumentError as error:
        return error.as_result()
    period = f"CY{year}Q4I" if resolved.instant else f"CY{year}"
    unit = resolved.unit or "USD"
    document: dict[str, Any] | None = None
    for tag in resolved.tags:
        candidate = sec.frame(resolved.taxonomy, tag, unit, period)
        if candidate is None:
            continue
        document = document or candidate
        if any(entry["cik"] == cik for entry in candidate.get("data", [])):
            document = candidate
            break
    if document is None:
        return {"error": "no_frame", "detail": f"The SEC has no {period} frame for {concept}."}
    data = sorted(document.get("data", []), key=lambda entry: entry["val"], reverse=True)
    logger.info("Frame %s %s fetched with %d filers", document.get("tag"), period, len(data))
    company = next((entry for entry in data if entry["cik"] == cik), None)
    admits = (
        f"balance sheet values at the fiscal year end nearest the end of calendar {year}"
        if resolved.instant
        else f"every fiscal year ending in calendar {year}"
    )
    return {
        "concept": document.get("tag"),
        "frame": period,
        "admits": admits,
        "filer_count": len(data),
        "median": float(statistics.median(entry["val"] for entry in data)) if data else None,
        "largest": [
            {"name": entry["entityName"], "value": entry["val"]} for entry in data[:LARGEST_SHOWN]
        ],
        "value": company["val"] if company else None,
        "rank": data.index(company) + 1 if company else None,
        "period_end": company.get("end") if company else None,
        "accession": company.get("accn") if company else None,
    }


@dataclass(frozen=True)
class ToolContext:
    facts: FactReader
    sec: SecClient
    cik: int


def analyst_tools(context: ToolContext) -> list[DecoratedFunctionTool[..., dict[str, Any]]]:
    concepts = ", ".join(ALIASES)

    @tool(name="query_facts")
    def query_facts_tool(
        concept: str, fiscal_year_from: int | None = None, fiscal_year_to: int | None = None
    ) -> dict[str, Any]:
        """Look up a reported figure for the company from its annual 10-K filings.

        Returns up to twelve rows, newest first, each with the value, unit, period, fiscal year,
        form and accession number. Cite the accession number for every figure you use. When a
        figure was reported in several filings, the latest filed value is returned.

        Args:
            concept: A concept name such as revenue, net_income, operating_income or
                total_assets, or an exact us-gaap tag.
            fiscal_year_from: First fiscal year to include, optional.
            fiscal_year_to: Last fiscal year to include, optional.
        """
        return query_facts(context.facts, context.cik, concept, fiscal_year_from, fiscal_year_to)

    @tool(name="compute_ratio")
    def compute_ratio_tool(ratio: str, fiscal_year: int | None = None) -> dict[str, Any]:
        """Compute a financial ratio for the company from its 10-K figures.

        Use this instead of doing arithmetic yourself. Returns the ratio as a decimal fraction,
        both figures it was computed from, and both accession numbers. The ratio is one of
        net_margin, operating_margin, gross_margin, revenue_growth, current_ratio or
        liabilities_to_assets.

        Args:
            ratio: The ratio name.
            fiscal_year: The fiscal year, optional; the latest year with both figures if omitted.
        """
        return compute_ratio(context.facts, context.cik, ratio, fiscal_year)

    query_facts_tool.tool_spec["description"] += f" Known concept names: {concepts}."
    return [query_facts_tool, compute_ratio_tool]


def ranking_tools(context: ToolContext) -> list[DecoratedFunctionTool[..., dict[str, Any]]]:
    @tool(name="frame_values")
    def frame_values_tool(concept: str, year: int) -> dict[str, Any]:
        """Rank the company among every SEC filer reporting a concept for one calendar year.

        Returns the company's value and rank, the number of filers, the median, and the five
        largest filers. The frame admits every fiscal year ending in that calendar year, so it
        is not a same-period or same-industry comparison.

        Args:
            concept: A concept name such as revenue, net_income or total_assets.
            year: The calendar year of the frame.
        """
        return frame_values(context.sec, context.cik, concept, year)

    return [frame_values_tool]
