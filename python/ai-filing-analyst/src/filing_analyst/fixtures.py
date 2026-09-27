"""The dated fixture cache: the SEC ticker list and the company facts of the example's
companies, written by `make fetch-fixtures` and checked against `MANIFEST.json`.

Run `python -m filing_analyst.fixtures check [DIR]` to re-hash the files without a network call.
"""

import gzip
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


MANIFEST_NAME = "MANIFEST.json"
TICKERS_NAME = "company_tickers.json.gz"
COMPANYFACTS_DIR = "companyfacts"


class FixtureMismatch(Exception):
    """A cached file is missing from the manifest or its hash does not match."""


@dataclass(frozen=True)
class TickerEntry:
    ticker: str
    cik: int
    name: str


def companyfacts_path(fixtures_dir: Path, cik: int) -> Path:
    return fixtures_dir / COMPANYFACTS_DIR / f"CIK{cik:010d}.json.gz"


def read_manifest(fixtures_dir: Path) -> dict[str, Any] | None:
    path = fixtures_dir / MANIFEST_NAME
    if not path.exists():
        return None
    manifest: dict[str, Any] = json.loads(path.read_text())
    return manifest


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _verified_bytes(fixtures_dir: Path, manifest: dict[str, Any], path: Path) -> bytes:
    name = str(path.relative_to(fixtures_dir))
    entry = manifest.get("files", {}).get(name)
    if entry is None:
        raise FixtureMismatch(f"{name} is not in {MANIFEST_NAME}")
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != entry["sha256"]:
        raise FixtureMismatch(f"{name} does not match its hash in {MANIFEST_NAME}")
    return data


class FactsCache:
    """Company facts from the cache, verified against the manifest on every read."""

    def __init__(self, fixtures_dir: Path) -> None:
        self._dir = fixtures_dir

    def read(self, cik: int) -> dict[str, Any] | None:
        path = companyfacts_path(self._dir, cik)
        manifest = read_manifest(self._dir)
        if manifest is None or not path.exists():
            return None
        document: dict[str, Any] = json.loads(
            gzip.decompress(_verified_bytes(self._dir, manifest, path))
        )
        return document


def parse_tickers(document: dict[str, Any]) -> list[TickerEntry]:
    """The SEC list is an object of `{"cik_str", "ticker", "title"}` entries keyed by index."""
    return [
        TickerEntry(ticker=entry["ticker"].upper(), cik=int(entry["cik_str"]), name=entry["title"])
        for entry in document.values()
    ]


def read_tickers(path: Path) -> list[TickerEntry]:
    raw = path.read_bytes()
    if path.suffix == ".gz":
        raw = gzip.decompress(raw)
    document: dict[str, Any] = json.loads(raw)
    return parse_tickers(document)


def check_fixtures(fixtures_dir: Path) -> list[str]:
    """Every problem with the cache, or an empty list."""
    manifest = read_manifest(fixtures_dir)
    if manifest is None:
        return [f"{MANIFEST_NAME} is missing"]
    problems = []
    listed = manifest.get("files", {})
    for name, entry in sorted(listed.items()):
        path = fixtures_dir / name
        if not path.exists():
            problems.append(f"{name} is missing")
        elif sha256_of(path) != entry["sha256"]:
            problems.append(f"{name} does not match its hash")
    for path in sorted((fixtures_dir / COMPANYFACTS_DIR).glob("*.json.gz")):
        if str(path.relative_to(fixtures_dir)) not in listed:
            problems.append(f"{path.relative_to(fixtures_dir)} is not in {MANIFEST_NAME}")
    return problems


def main(argv: list[str]) -> int:
    if len(argv) < 1 or argv[0] != "check":
        print("usage: python -m filing_analyst.fixtures check [DIR]", file=sys.stderr)
        return 2
    fixtures_dir = Path(argv[1]) if len(argv) > 1 else Path("fixtures")
    problems = check_fixtures(fixtures_dir)
    for problem in problems:
        print(problem)
    if not problems:
        manifest = read_manifest(fixtures_dir) or {}
        print(f"{len(manifest.get('files', {}))} files match {MANIFEST_NAME}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
