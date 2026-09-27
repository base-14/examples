"""The concept names the model may use, and the XBRL tags behind each.

A friendly name maps to one or more tags in priority order: companies moved revenue from
`SalesRevenueNet` to the ASC 606 tag around 2018, and a query spans both. The model may also
pass a us-gaap tag directly; anything outside `CONCEPT_PATTERN` is refused.
"""

import re
from dataclasses import dataclass
from datetime import date


CONCEPT_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]{1,99}$")
FIRST_XBRL_YEAR = 2009


@dataclass(frozen=True)
class Concept:
    name: str
    tags: tuple[str, ...]
    taxonomy: str = "us-gaap"
    unit: str | None = "USD"
    instant: bool | None = False


def _alias(name: str, *tags: str, unit: str = "USD", instant: bool = False) -> Concept:
    return Concept(name=name, tags=tags, unit=unit, instant=instant)


ALIASES: dict[str, Concept] = {
    concept.name: concept
    for concept in (
        _alias(
            "revenue",
            "RevenueFromContractWithCustomerExcludingAssessedTax",
            "Revenues",
            "SalesRevenueNet",
            "RevenueFromContractWithCustomerIncludingAssessedTax",
        ),
        _alias("cost_of_revenue", "CostOfRevenue", "CostOfGoodsAndServicesSold"),
        _alias("gross_profit", "GrossProfit"),
        _alias("operating_income", "OperatingIncomeLoss"),
        _alias("net_income", "NetIncomeLoss", "ProfitLoss"),
        _alias("rd_expense", "ResearchAndDevelopmentExpense"),
        _alias("operating_cash_flow", "NetCashProvidedByUsedInOperatingActivities"),
        _alias("eps_basic", "EarningsPerShareBasic", unit="USD/shares"),
        _alias("eps_diluted", "EarningsPerShareDiluted", unit="USD/shares"),
        _alias("total_assets", "Assets", instant=True),
        _alias("total_liabilities", "Liabilities", instant=True),
        _alias("current_assets", "AssetsCurrent", instant=True),
        _alias("current_liabilities", "LiabilitiesCurrent", instant=True),
        _alias("stockholders_equity", "StockholdersEquity", instant=True),
        _alias("cash", "CashAndCashEquivalentsAtCarryingValue", instant=True),
        Concept("public_float", ("EntityPublicFloat",), taxonomy="dei", instant=True),
    )
}


class ArgumentError(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail

    def as_result(self) -> dict[str, str]:
        return {"error": self.code, "detail": self.detail}


def resolve_concept(name: str) -> Concept:
    """An alias, or a us-gaap tag passed as is with its unit and period type left open."""
    if not CONCEPT_PATTERN.fullmatch(name):
        raise ArgumentError(
            "invalid_concept",
            f"{name[:40]!r} is not a concept name. Use one of: {', '.join(ALIASES)}.",
        )
    alias = ALIASES.get(name.lower())
    if alias is not None:
        return alias
    return Concept(name=name, tags=(name,), unit=None, instant=None)


def check_year(year: int | None) -> None:
    latest = date.today().year + 1
    if year is not None and not FIRST_XBRL_YEAR <= year <= latest:
        raise ArgumentError(
            "invalid_year", f"{year} is outside {FIRST_XBRL_YEAR} to {latest}, the XBRL years."
        )
