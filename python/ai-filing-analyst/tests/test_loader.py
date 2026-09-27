import json
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

from filing_analyst.loader import ensure_facts


if TYPE_CHECKING:
    from filing_analyst.facts import FactRow


RECORDED = json.loads(
    (Path(__file__).parent / "fixtures" / "companyfacts" / "CIK0001445305.json").read_text()
)


class MemoryCompany:
    def __init__(self, store: MemoryStore, cik: int) -> None:
        self._store = store
        self._cik = cik

    def is_loaded(self) -> bool:
        return self._store.is_loaded(self._cik)

    def write(self, rows: Sequence[FactRow], source: str) -> None:
        self._store.loads[self._cik] = (source, len(rows))


class MemoryStore:
    def __init__(self) -> None:
        self.loads: dict[int, tuple[str, int]] = {}

    def is_loaded(self, cik: int) -> bool:
        return cik in self.loads

    @contextmanager
    def locked(self, cik: int) -> Iterator[MemoryCompany]:
        yield MemoryCompany(self, cik)


class StubCache:
    def __init__(self, documents: dict[int, dict[str, Any]]) -> None:
        self.documents = documents

    def read(self, cik: int) -> dict[str, Any] | None:
        return self.documents.get(cik)


class StubSec:
    def __init__(self, document: dict[str, Any] | None) -> None:
        self.document = document
        self.calls: list[int] = []

    def company_facts(self, cik: int) -> dict[str, Any] | None:
        self.calls.append(cik)
        return self.document


def test_a_cached_company_loads_with_no_sec_call() -> None:
    store, sec = MemoryStore(), StubSec(None)
    result = ensure_facts(store, StubCache({1445305: RECORDED}), sec, 1445305)
    assert (result.source, result.rows) == ("cache", 677)
    assert sec.calls == []
    assert store.loads[1445305] == ("cache", 677)


def test_a_company_outside_the_cache_goes_to_the_sec() -> None:
    store, sec = MemoryStore(), StubSec(RECORDED)
    result = ensure_facts(store, StubCache({}), sec, 1432133)
    assert (result.source, result.rows) == ("sec", 677)
    assert sec.calls == [1432133]


def test_a_loaded_company_reads_from_the_store() -> None:
    store, sec = MemoryStore(), StubSec(RECORDED)
    store.loads[1445305] = ("cache", 677)
    result = ensure_facts(store, StubCache({}), sec, 1445305)
    assert (result.source, result.rows) == ("stored", 0)
    assert sec.calls == []


def test_a_company_with_no_sec_facts_is_recorded_empty() -> None:
    store = MemoryStore()
    result = ensure_facts(store, StubCache({}), StubSec(None), 99)
    assert (result.source, result.rows) == ("sec", 0)
    assert store.loads[99] == ("sec", 0)
