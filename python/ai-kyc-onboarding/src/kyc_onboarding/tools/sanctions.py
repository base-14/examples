from typing import Any, Literal

import psycopg
from pydantic import BaseModel


SanctionsResult = Literal["clear", "partial", "exact"]

DEFAULT_PARTIAL_THRESHOLD = 0.4


class SanctionsScreeningResult(BaseModel):
    result: SanctionsResult
    matched_entry: str | None
    score: float | None


def screen_sanctions(
    name: str,
    dsn: str | psycopg.Connection[Any],
    *,
    partial_threshold: float = DEFAULT_PARTIAL_THRESHOLD,
) -> SanctionsScreeningResult:
    if isinstance(dsn, str):
        with psycopg.connect(dsn, connect_timeout=5) as connection:
            return _screen(connection, name, partial_threshold)
    return _screen(dsn, name, partial_threshold)


def _screen(
    connection: psycopg.Connection[Any], name: str, partial_threshold: float
) -> SanctionsScreeningResult:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT full_name FROM sanctions WHERE lower(full_name) = lower(%s) LIMIT 1",
            (name,),
        )
        exact_row = cursor.fetchone()
        if exact_row is not None:
            return SanctionsScreeningResult(result="exact", matched_entry=exact_row[0], score=1.0)

        cursor.execute(
            "SELECT full_name, similarity(full_name, %s) AS score "
            "FROM sanctions ORDER BY score DESC LIMIT 1",
            (name,),
        )
        best_row = cursor.fetchone()
        if best_row is None:
            return SanctionsScreeningResult(result="clear", matched_entry=None, score=None)

        matched_entry, score = best_row
        if score >= partial_threshold:
            return SanctionsScreeningResult(
                result="partial", matched_entry=matched_entry, score=score
            )
        return SanctionsScreeningResult(result="clear", matched_entry=matched_entry, score=score)
