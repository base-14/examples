"""Checks the analyst's answer against the tool results of the same run.

An answer passes when every figure and accession number came back from a tool, every ratio came
from `compute_ratio`, and every number in the text matches a figure, a ratio, or a ranking
statistic from `frame_values`. A number in the text may be rounded: it matches when it is within
one unit of its last shown digit, after its scale (thousand, million, billion, percent) is
applied. Signs are ignored, since a text says "a loss of $55 million" for -55,042,000. Years,
dates, counts under one hundred and accession numbers in the text are not checked.
"""

import json
import re
from collections.abc import Iterator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from strands.hooks import AfterToolCallEvent, HookProvider, HookRegistry


if TYPE_CHECKING:
    from filing_analyst.answer import FilingAnswer


GROUNDING_TOOLS = frozenset({"query_facts", "compute_ratio", "frame_values"})
RATIO_TOLERANCE = 1e-4
SMALL_COUNT_LIMIT = 100
YEARS = range(1900, 2101)
SCALES = {
    "%": 0.01,
    "percent": 0.01,
    "k": 1e3,
    "thousand": 1e3,
    "m": 1e6,
    "million": 1e6,
    "b": 1e9,
    "billion": 1e9,
    "trillion": 1e12,
}
UNCHECKED = re.compile(r"\d{10}-\d{2}-\d{6}|\d{4}-\d{2}-\d{2}")
NUMBER = re.compile(
    r"(?<![\w.])(?P<currency>-?\$)?-?"
    r"(?P<number>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
    r"\s?(?P<scale>%|percent\b|thousand\b|million\b|billion\b|trillion\b|[KMB]\b)?",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Verdict:
    passed: bool
    reason: str | None
    figure_count: int
    citations_verified: int


class ToolResultCollector(HookProvider):
    """Collects the JSON results of the grounding tools for one request. Registered on both
    agents, because the ranking agent's `frame_values` calls run inside its own agent."""

    def __init__(self) -> None:
        self.results: list[dict[str, Any]] = []
        self.failed_tools: set[str] = set()

    def register_hooks(self, registry: HookRegistry, **kwargs: Any) -> None:
        registry.add_callback(AfterToolCallEvent, self.collect)

    def collect(self, event: AfterToolCallEvent) -> None:
        name = event.tool_use["name"]
        if name not in GROUNDING_TOOLS:
            return
        if event.result["status"] != "success":
            self.failed_tools.add(name)
            return
        for block in event.result["content"]:
            try:
                parsed = json.loads(block.get("text", ""))
            except ValueError:
                continue
            if isinstance(parsed, dict) and "error" not in parsed:
                self.results.append(parsed)


def _close(a: float, b: float, tolerance: float = 1e-9) -> bool:
    return abs(a - b) <= max(tolerance, tolerance * abs(b))


def _walk(node: Any) -> Iterator[dict[str, Any]]:
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _walk(value)
    elif isinstance(node, list):
        for value in node:
            yield from _walk(value)


def _cited_values(results: list[dict[str, Any]]) -> list[tuple[float, str, int | None]]:
    """Each returned value with its accession and, when the tool gave one, its fiscal year."""
    return [
        (float(node["value"]), str(node["accession"]), node.get("fiscal_year"))
        for result in results
        for node in _walk(result)
        if isinstance(node.get("value"), (int, float)) and node.get("accession")
    ]


def _run_accessions(results: list[dict[str, Any]]) -> set[str]:
    accessions: set[str] = set()
    for result in results:
        for node in _walk(result):
            if node.get("accession"):
                accessions.add(str(node["accession"]))
            accessions.update(str(a) for a in node.get("accessions", []))
    return accessions


def _ranking_numbers(results: list[dict[str, Any]]) -> list[float]:
    numbers: list[float] = []
    for result in results:
        if "frame" not in result:
            continue
        for key in ("filer_count", "median", "rank", "value"):
            if isinstance(result.get(key), (int, float)):
                numbers.append(float(result[key]))
        numbers.extend(float(entry["value"]) for entry in result.get("largest", []))
    return numbers


def _text_numbers(text: str) -> Iterator[tuple[float, float, int]]:
    """Each checked number as (shown value, scale, decimals shown)."""
    for match in NUMBER.finditer(UNCHECKED.sub(" ", text)):
        shown = match["number"].replace(",", "")
        scale_word = (match["scale"] or "").lower()
        value = float(shown)
        decimals = len(shown.split(".", 1)[1]) if "." in shown else 0
        plain = not match["currency"] and not scale_word and decimals == 0
        if plain and (value < SMALL_COUNT_LIMIT or int(value) in YEARS):
            continue
        yield value, SCALES.get(scale_word, 1.0), decimals


def _matches(shown: float, scale: float, decimals: int, grounded: list[float]) -> bool:
    step = 10.0**-decimals
    return any(abs(shown - abs(number) / scale) < step - 1e-12 for number in grounded)


def verify_answer(answer: FilingAnswer, results: list[dict[str, Any]]) -> Verdict:
    accessions = _run_accessions(results)
    cited = _cited_values(results)

    def verdict(reason: str | None, verified: int) -> Verdict:
        return Verdict(reason is None, reason, len(answer.figures), verified)

    for verified, figure in enumerate(answer.figures):
        if figure.accession not in accessions:
            return verdict("accession_not_in_run", verified)
        if not any(
            accession == figure.accession
            and _close(figure.value, value)
            and fiscal_year in (None, figure.fiscal_year)
            for value, accession, fiscal_year in cited
        ):
            return verdict("figure_not_returned", verified)
    computed = [r for r in results if "ratio" in r and isinstance(r.get("value"), (int, float))]
    for ratio in answer.ratios:
        if not any(
            abs(ratio.value - float(r["value"])) <= RATIO_TOLERANCE
            and ratio.accessions
            and set(ratio.accessions) <= set(r["accessions"])
            for r in computed
        ):
            return verdict("ratio_not_computed", len(answer.figures))
    grounded = [
        *(figure.value for figure in answer.figures),
        *(ratio.value for ratio in answer.ratios),
        *_ranking_numbers(results),
    ]
    for shown, scale, decimals in _text_numbers(answer.answer):
        if not _matches(shown, scale, decimals, grounded):
            return verdict("number_not_in_figures", len(answer.figures))
    return verdict(None, len(answer.figures))
