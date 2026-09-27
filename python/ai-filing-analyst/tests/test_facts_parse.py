import json
from collections import Counter
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from filing_analyst.facts import parse_company_facts


FIXTURES = Path(__file__).parent / "fixtures" / "companyfacts"
WORKIVA = 1445305
AMPLITUDE = 1866692
RINGCENTRAL = 1384905


def recorded(cik: int) -> dict[str, Any]:
    document: dict[str, Any] = json.loads((FIXTURES / f"CIK{cik:010d}.json").read_text())
    return document


def test_only_us_gaap_and_dei_in_the_four_units_are_kept() -> None:
    rows = parse_company_facts(recorded(WORKIVA))
    assert Counter(row.unit for row in rows) == {
        "USD": 502,
        "shares": 71,
        "USD/shares": 71,
        "pure": 33,
    }
    assert {row.taxonomy for row in rows} == {"us-gaap", "dei"}


def test_row_counts_for_amplitude_and_ringcentral() -> None:
    assert len(parse_company_facts(recorded(AMPLITUDE))) == 209 + 15 + 52 + 52
    assert len(parse_company_facts(recorded(RINGCENTRAL))) == 631 + 79 + 8 + 79


def test_an_instant_has_no_start_and_a_duration_keeps_its_start() -> None:
    rows = parse_company_facts(recorded(WORKIVA))
    assets = [r for r in rows if r.concept == "Assets" and r.period_end == date(2022, 12, 31)]
    assert assets
    assert all(r.period_start is None for r in assets)

    quarter_and_half_year = {
        r.period_start
        for r in rows
        if r.concept == "NetIncomeLoss"
        and r.period_end == date(2014, 6, 30)
        and r.accession == "0001445305-15-000066"
    }
    assert quarter_and_half_year == {date(2014, 4, 1), date(2014, 1, 1)}


def test_a_comparative_row_keeps_the_filing_year_apart_from_its_period() -> None:
    rows = parse_company_facts(recorded(WORKIVA))
    (row,) = [
        r
        for r in rows
        if r.concept == "NetIncomeLoss"
        and r.period_start == date(2021, 1, 1)
        and r.period_end == date(2021, 12, 31)
        and r.accession == "0001445305-24-000021"
    ]
    assert row.filing_fy == 2023
    assert row.period_end.year == 2021
    assert row.value == Decimal(-37730000)
    assert row.form == "10-K"
    assert row.filed == date(2024, 2, 20)


def test_a_duplicate_key_in_one_filing_is_stored_once() -> None:
    fact = {"end": "2024-12-31", "val": 5, "accn": "a-1", "fy": 2024, "fp": "FY"}
    document = {
        "cik": "0000000001",
        "facts": {
            "us-gaap": {
                "Assets": {
                    "units": {
                        "USD": [
                            {**fact, "form": "10-K", "filed": "2025-02-01"},
                            {**fact, "form": "10-K", "filed": "2025-02-01", "frame": "CY2024Q4I"},
                        ]
                    }
                }
            }
        },
    }
    (row,) = parse_company_facts(document)
    assert row.frame == "CY2024Q4I"


def test_a_document_without_facts_parses_to_nothing() -> None:
    assert parse_company_facts({"cik": 1, "facts": {}}) == []
