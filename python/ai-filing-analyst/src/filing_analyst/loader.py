"""Loads a company's facts into the store once, before the agent starts."""

import logging
from collections.abc import Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from filing_analyst.app_metrics import FACTS_LOADED
from filing_analyst.facts import FactRow, FactSource, parse_company_facts


logger = logging.getLogger(__name__)


class LockedCompany(Protocol):
    def is_loaded(self) -> bool: ...

    def write(self, rows: Sequence[FactRow], source: FactSource) -> None: ...


class FactStore(Protocol):
    def is_loaded(self, cik: int) -> bool: ...

    def locked(self, cik: int) -> AbstractContextManager[LockedCompany]: ...


class CompanyFactsCache(Protocol):
    def read(self, cik: int) -> dict[str, Any] | None: ...


class CompanyFactsSource(Protocol):
    def company_facts(self, cik: int) -> Any: ...


@dataclass(frozen=True)
class LoadResult:
    source: Literal["stored", "cache", "sec"]
    rows: int


def ensure_facts(
    store: FactStore, cache: CompanyFactsCache, sec: CompanyFactsSource, cik: int
) -> LoadResult:
    """Load the company's facts unless they are on file. The per-company lock makes two first
    questions on one company load it once: the second waits, checks again and finds it."""
    if store.is_loaded(cik):
        return LoadResult("stored", 0)
    with store.locked(cik) as company:
        if company.is_loaded():
            return LoadResult("stored", 0)
        document = cache.read(cik)
        source: FactSource = "cache"
        if document is None:
            document = sec.company_facts(cik)
            source = "sec"
        rows = parse_company_facts(document) if document else []
        company.write(rows, source)
    FACTS_LOADED.add(len(rows))
    logger.info("Facts loaded for CIK %d from %s: %d rows", cik, source, len(rows))
    return LoadResult(source, len(rows))
