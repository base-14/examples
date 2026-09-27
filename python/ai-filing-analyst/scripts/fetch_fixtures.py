"""Fetch the SEC ticker list and the company facts of the companies in
`fixtures/companies.txt`, and write them to the fixture cache.

Every file is written to a staging directory first. Only when every fetch has succeeded are the
files moved into place, with `MANIFEST.json` last, so a failed run leaves the old cache as it
was. The SEC client applies the User-Agent, the token bucket, the retries and the 403 back-off.
"""

import gzip
import hashlib
import json
import shutil
import sys
import tempfile
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

from filing_analyst.config import Settings, SettingsError, get_settings
from filing_analyst.fixtures import (
    COMPANYFACTS_DIR,
    MANIFEST_NAME,
    TICKERS_NAME,
    companyfacts_path,
    parse_tickers,
)
from filing_analyst.sec_client import SEC_DATA, SEC_WWW, SecClient, SecError


COMPANY_LIST_NAME = "companies.txt"


class UnknownTicker(Exception):
    pass


def read_company_list(path: Path) -> list[str]:
    lines = (line.split("#", 1)[0].strip().upper() for line in path.read_text().splitlines())
    return [line for line in lines if line]


def _write_gzip_json(path: Path, document: Any) -> bytes:
    data = gzip.compress(json.dumps(document, separators=(",", ":")).encode(), mtime=0)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return data


def _entry(url: str, data: bytes) -> dict[str, Any]:
    return {"url": url, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def fetch_fixtures(
    client: SecClient,
    fixtures_dir: Path,
    tickers: list[str],
    *,
    fetched: str,
    report: Callable[[str], None],
) -> None:
    fixtures_dir.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".staging-", dir=fixtures_dir))
    try:
        ticker_document = client.company_tickers()
        ciks = {entry.ticker: entry.cik for entry in parse_tickers(ticker_document)}
        unknown = [ticker for ticker in tickers if ticker not in ciks]
        if unknown:
            raise UnknownTicker(f"not in the SEC ticker list: {', '.join(unknown)}")

        files: dict[str, dict[str, Any]] = {}
        data = _write_gzip_json(staging / TICKERS_NAME, ticker_document)
        files[TICKERS_NAME] = _entry(f"{SEC_WWW}/files/company_tickers.json", data)
        report(f"{TICKERS_NAME}  {len(data)} bytes")

        for ticker in tickers:
            cik = ciks[ticker]
            document = client.company_facts(cik)
            if document is None:
                raise UnknownTicker(f"{ticker} (CIK {cik}) has no company facts at the SEC")
            name = str(companyfacts_path(fixtures_dir, cik).relative_to(fixtures_dir))
            data = _write_gzip_json(staging / name, document)
            files[name] = _entry(f"{SEC_DATA}/api/xbrl/companyfacts/CIK{cik:010d}.json", data)
            report(f"{name}  {ticker}  {len(data)} bytes")

        manifest = {
            "fetched": fetched,
            "source": "SEC EDGAR XBRL APIs",
            "tickers": {ticker: ciks[ticker] for ticker in tickers},
            "files": files,
        }
        (staging / MANIFEST_NAME).write_text(json.dumps(manifest, indent=2) + "\n")

        (fixtures_dir / COMPANYFACTS_DIR).mkdir(exist_ok=True)
        for name in files:
            (staging / name).replace(fixtures_dir / name)
        (staging / MANIFEST_NAME).replace(fixtures_dir / MANIFEST_NAME)
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def build_client(settings: Settings) -> SecClient:
    return SecClient(
        settings.sec_user_agent,
        settings.sec_requests_per_second,
        settings.sec_backoff_seconds,
    )


def main(argv: list[str]) -> int:
    try:
        settings = get_settings()
    except SettingsError as error:
        print(f"fetch-fixtures: {error}", file=sys.stderr)
        return 2
    tickers = read_company_list(settings.fixtures_dir / COMPANY_LIST_NAME)
    client = build_client(settings)
    try:
        fetch_fixtures(
            client,
            settings.fixtures_dir,
            tickers,
            fetched=date.today().isoformat(),
            report=print,
        )
    except (UnknownTicker, SecError) as error:
        print(f"fetch-fixtures: {error}; the cache is unchanged", file=sys.stderr)
        return 1
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
