"""Postgres access for companies, tickers and facts. Every query is parameterised."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING

import psycopg

from filing_analyst.facts import FactRow


if TYPE_CHECKING:
    from filing_analyst.facts import FactSource
    from filing_analyst.fixtures import TickerEntry


CONNECT_TIMEOUT_SECONDS = 5

UPSERT_FACT = """
INSERT INTO facts (cik, taxonomy, concept, unit, period_start, period_end, value,
                   filing_fy, filing_fp, form, filed, accession, frame)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT ON CONSTRAINT facts_identity DO UPDATE
SET value = EXCLUDED.value, filing_fy = EXCLUDED.filing_fy, filing_fp = EXCLUDED.filing_fp,
    form = EXCLUDED.form, filed = EXCLUDED.filed, frame = EXCLUDED.frame
"""


SELECT_FACTS = """
SELECT taxonomy, concept, unit, period_start, period_end, value, filing_fy, filing_fp, form,
       filed, accession, frame
FROM facts
WHERE cik = %s AND taxonomy = %s AND concept = ANY(%s)
"""


@dataclass(frozen=True)
class Company:
    cik: int
    name: str


class PostgresCompany:
    def __init__(self, connection: psycopg.Connection, cik: int) -> None:
        self._connection = connection
        self._cik = cik

    def is_loaded(self) -> bool:
        row = self._connection.execute(
            "SELECT 1 FROM fact_loads WHERE cik = %s", (self._cik,)
        ).fetchone()
        return row is not None

    def write(self, rows: Sequence[FactRow], source: FactSource) -> None:
        with self._connection.cursor() as cursor:
            cursor.executemany(
                UPSERT_FACT,
                [
                    (
                        self._cik,
                        r.taxonomy,
                        r.concept,
                        r.unit,
                        r.period_start,
                        r.period_end,
                        r.value,
                        r.filing_fy,
                        r.filing_fp,
                        r.form,
                        r.filed,
                        r.accession,
                        r.frame,
                    )
                    for r in rows
                ],
            )
            cursor.execute(
                "INSERT INTO fact_loads (cik, source, row_count) VALUES (%s, %s, %s)",
                (self._cik, source, len(rows)),
            )


class PostgresStore:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    def connect(self) -> psycopg.Connection:
        return psycopg.connect(self._dsn, connect_timeout=CONNECT_TIMEOUT_SECONDS)

    def load_tickers(self, entries: Sequence[TickerEntry]) -> None:
        """Upsert the ticker list. Two share classes on one CIK make one company."""
        companies = {entry.cik: entry.name for entry in entries}
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.executemany(
                "INSERT INTO companies (cik, name) VALUES (%s, %s) "
                "ON CONFLICT (cik) DO UPDATE SET name = EXCLUDED.name",
                list(companies.items()),
            )
            cursor.executemany(
                "INSERT INTO tickers (ticker, cik) VALUES (%s, %s) "
                "ON CONFLICT (ticker) DO UPDATE SET cik = EXCLUDED.cik",
                [(entry.ticker, entry.cik) for entry in entries],
            )

    def resolve_ticker(self, ticker: str) -> Company | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT c.cik, c.name FROM tickers t JOIN companies c USING (cik) "
                "WHERE t.ticker = %s",
                (ticker.strip().upper(),),
            ).fetchone()
        return Company(cik=row[0], name=row[1]) if row else None

    def is_loaded(self, cik: int) -> bool:
        with self.connect() as connection:
            return PostgresCompany(connection, cik).is_loaded()

    def facts(self, cik: int, taxonomy: str, concepts: Sequence[str]) -> list[FactRow]:
        with self.connect() as connection:
            rows = connection.execute(SELECT_FACTS, (cik, taxonomy, list(concepts))).fetchall()
        return [FactRow(*row) for row in rows]

    @contextmanager
    def locked(self, cik: int) -> Iterator[PostgresCompany]:
        """One transaction holding the company's advisory lock until it commits."""
        with self.connect() as connection, connection.transaction():
            connection.execute("SELECT pg_advisory_xact_lock(%s)", (cik,))
            yield PostgresCompany(connection, cik)
