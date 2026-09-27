"""Against the Compose Postgres: `make docker-up`, then `make test-integration`."""

import json
import os
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import psycopg
import pytest

from filing_analyst.fixtures import read_tickers
from filing_analyst.loader import ensure_facts
from filing_analyst.store import PostgresStore
from filing_analyst.tools import query_facts


pytestmark = pytest.mark.integration

FIXTURES = Path(__file__).parent / "fixtures"
DSN = os.environ.get("FILING_DB_DSN", "postgresql://filing:filing@localhost:5433/filing")
ALPHABET = 1652044
WORKIVA = 1445305
RECORDED = json.loads((FIXTURES / "companyfacts" / f"CIK{WORKIVA:010d}.json").read_text())


class NoCache:
    def read(self, cik: int) -> dict[str, Any] | None:
        return None


class SlowSec:
    def __init__(self, document: dict[str, Any]) -> None:
        self.document = document
        self.calls = 0
        self._lock = threading.Lock()

    def company_facts(self, cik: int) -> dict[str, Any]:
        with self._lock:
            self.calls += 1
        time.sleep(0.3)
        return self.document


@pytest.fixture
def store() -> Iterator[PostgresStore]:
    store = PostgresStore(DSN)
    store.load_tickers(read_tickers(FIXTURES / "company_tickers.json"))
    with psycopg.connect(DSN) as connection:
        for table in ("facts", "fact_loads"):
            connection.execute(
                f"DELETE FROM {table} WHERE cik = ANY(%s)",
                ([ALPHABET, WORKIVA],),
            )
    yield store


def test_both_alphabet_tickers_resolve_to_one_company_and_one_load(store: PostgresStore) -> None:
    googl, goog = store.resolve_ticker("GOOGL"), store.resolve_ticker("goog")
    assert googl is not None and goog is not None
    assert googl.cik == goog.cik == ALPHABET

    sec = SlowSec({"cik": ALPHABET, "facts": {}})
    assert ensure_facts(store, NoCache(), sec, googl.cik).source == "sec"
    assert ensure_facts(store, NoCache(), sec, goog.cik).source == "stored"
    assert sec.calls == 1


def test_two_concurrent_first_loads_fetch_once(store: PostgresStore) -> None:
    sec = SlowSec(RECORDED)
    results = []

    def load() -> None:
        results.append(ensure_facts(store, NoCache(), sec, WORKIVA))

    threads = [threading.Thread(target=load) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sec.calls == 1
    assert sorted(result.source for result in results) == ["sec", "stored"]
    with psycopg.connect(DSN) as connection:
        row = connection.execute(
            "SELECT count(*), (SELECT row_count FROM fact_loads WHERE cik = %s) "
            "FROM facts WHERE cik = %s",
            (WORKIVA, WORKIVA),
        ).fetchone()
    assert row == (677, 677)


def test_a_ticker_carrying_sql_is_just_an_unknown_ticker(store: PostgresStore) -> None:
    assert store.resolve_ticker("WK'; DROP TABLE facts; --") is None
    assert store.resolve_ticker("WK") is not None


def test_tools_read_the_stored_facts(store: PostgresStore) -> None:
    ensure_facts(store, NoCache(), SlowSec(RECORDED), WORKIVA)
    (row,) = query_facts(store, WORKIVA, "net_income", 2019, 2019)["rows"]
    assert (row["value"], row["accession"]) == (-47479000, "0001445305-22-000041")
    assert query_facts(store, WORKIVA, "Revenue'--")["error"] == "invalid_concept"
