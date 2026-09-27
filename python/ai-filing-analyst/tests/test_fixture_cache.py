import gzip
import hashlib
import json
from pathlib import Path

import pytest

from filing_analyst.fixtures import (
    FactsCache,
    FixtureMismatch,
    check_fixtures,
    companyfacts_path,
    read_tickers,
)


DOCUMENT = {"cik": 1445305, "facts": {}}


def write_cache(root: Path, documents: dict[int, dict[str, object]]) -> None:
    files = {}
    for cik, document in documents.items():
        path = companyfacts_path(root, cik)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(gzip.compress(json.dumps(document).encode()))
        files[str(path.relative_to(root))] = {
            "url": f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json",
            "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    (root / "MANIFEST.json").write_text(json.dumps({"fetched": "2026-09-26", "files": files}))


def test_a_cached_company_reads_back(tmp_path: Path) -> None:
    write_cache(tmp_path, {1445305: DOCUMENT})
    assert FactsCache(tmp_path).read(1445305) == DOCUMENT


def test_a_company_outside_the_cache_reads_none(tmp_path: Path) -> None:
    write_cache(tmp_path, {1445305: DOCUMENT})
    assert FactsCache(tmp_path).read(1432133) is None


def test_no_manifest_means_no_cache(tmp_path: Path) -> None:
    assert FactsCache(tmp_path).read(1445305) is None


def test_a_tampered_file_is_refused(tmp_path: Path) -> None:
    write_cache(tmp_path, {1445305: DOCUMENT})
    companyfacts_path(tmp_path, 1445305).write_bytes(gzip.compress(b'{"cik": 1, "facts": {}}'))
    with pytest.raises(FixtureMismatch):
        FactsCache(tmp_path).read(1445305)
    assert check_fixtures(tmp_path) != []


def test_a_file_the_manifest_does_not_list_is_refused(tmp_path: Path) -> None:
    write_cache(tmp_path, {})
    path = companyfacts_path(tmp_path, 1445305)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(gzip.compress(json.dumps(DOCUMENT).encode()))
    with pytest.raises(FixtureMismatch):
        FactsCache(tmp_path).read(1445305)


def test_check_passes_on_an_intact_cache(tmp_path: Path) -> None:
    write_cache(tmp_path, {1445305: DOCUMENT, 1866692: DOCUMENT})
    assert check_fixtures(tmp_path) == []


def test_tickers_read_from_the_sec_list_shape() -> None:
    tickers = read_tickers(Path(__file__).parent / "fixtures" / "company_tickers.json")
    by_ticker = {t.ticker: t for t in tickers}
    assert by_ticker["GOOGL"].cik == by_ticker["GOOG"].cik == 1652044
    assert by_ticker["WK"].name == "WORKIVA INC"
