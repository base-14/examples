import json
from pathlib import Path

import httpx
import pytest

from filing_analyst.fixtures import MANIFEST_NAME, check_fixtures, companyfacts_path
from filing_analyst.sec_client import SecBlocked
from scripts.fetch_fixtures import UnknownTicker, fetch_fixtures, main
from tests.sec_support import FakeClock, RecordingHandler, sec_client


COMPANIES = {
    "ABNB": 1559720,
    "WK": 1445305,
    "GTLB": 1653482,
    "FRSH": 1544522,
    "AMPL": 1866692,
    "KVYO": 1835830,
    "MNDY": 1845338,
}
TICKERS = {
    str(i): {"cik_str": cik, "ticker": ticker, "title": f"{ticker} Inc."}
    for i, (ticker, cik) in enumerate(COMPANIES.items())
}


def sec(blocked_cik: int | None = None) -> RecordingHandler:
    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("company_tickers.json"):
            return httpx.Response(200, json=TICKERS)
        cik = int(request.url.path.rsplit("CIK", 1)[1].removesuffix(".json"))
        if cik == blocked_cik:
            return httpx.Response(403)
        return httpx.Response(200, json={"cik": cik, "facts": {}})

    return RecordingHandler(respond)


def run(root: Path, handler: RecordingHandler, tickers: list[str] | None = None) -> list[str]:
    lines: list[str] = []
    fetch_fixtures(
        sec_client(handler, FakeClock()),
        root,
        tickers or list(COMPANIES),
        fetched="2026-09-26",
        report=lines.append,
    )
    return lines


def test_a_clean_run_writes_every_file_and_the_manifest(tmp_path: Path) -> None:
    lines = run(tmp_path, sec())
    manifest = json.loads((tmp_path / MANIFEST_NAME).read_text())
    assert manifest["fetched"] == "2026-09-26"
    assert manifest["tickers"] == COMPANIES
    assert len(manifest["files"]) == 8
    for cik in COMPANIES.values():
        assert companyfacts_path(tmp_path, cik).exists()
    assert check_fixtures(tmp_path) == []
    assert len(lines) == 8
    assert not list(tmp_path.glob(".staging*"))


def test_a_rerun_with_unchanged_data_writes_identical_bytes(tmp_path: Path) -> None:
    run(tmp_path, sec())
    first = (tmp_path / MANIFEST_NAME).read_text()
    run(tmp_path, sec())
    assert (tmp_path / MANIFEST_NAME).read_text() == first


def test_a_403_on_the_third_company_leaves_the_old_cache_untouched(tmp_path: Path) -> None:
    run(tmp_path, sec())
    manifest_before = (tmp_path / MANIFEST_NAME).read_bytes()
    first_file = companyfacts_path(tmp_path, COMPANIES["ABNB"]).read_bytes()

    handler = sec(blocked_cik=COMPANIES["GTLB"])
    with pytest.raises(SecBlocked):
        fetch_fixtures(
            sec_client(handler, FakeClock()),
            tmp_path,
            list(COMPANIES),
            fetched="2026-10-01",
            report=lambda _line: None,
        )
    assert (tmp_path / MANIFEST_NAME).read_bytes() == manifest_before
    assert companyfacts_path(tmp_path, COMPANIES["ABNB"]).read_bytes() == first_file
    assert check_fixtures(tmp_path) == []
    assert not list(tmp_path.glob(".staging*"))
    assert len(handler.requests) == 4


def test_an_unknown_ticker_stops_before_any_company_fetch(tmp_path: Path) -> None:
    handler = sec()
    with pytest.raises(UnknownTicker):
        run(tmp_path, handler, ["WK", "NOPE"])
    assert len(handler.requests) == 1
    assert not (tmp_path / MANIFEST_NAME).exists()


def test_a_tampered_file_fails_the_check(tmp_path: Path) -> None:
    run(tmp_path, sec())
    companyfacts_path(tmp_path, COMPANIES["WK"]).write_bytes(b"tampered")
    assert check_fixtures(tmp_path) == [
        "companyfacts/CIK0001445305.json.gz does not match its hash"
    ]


def test_main_refuses_without_a_user_agent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("SEC_USER_AGENT", raising=False)
    monkeypatch.setenv("FIXTURES_DIR", str(tmp_path))
    assert main([]) == 2
    assert "SEC_USER_AGENT" in capsys.readouterr().err
    assert list(tmp_path.iterdir()) == []


def test_main_exits_non_zero_on_an_unknown_ticker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("SEC_USER_AGENT", "Example Co ops@example.com")
    monkeypatch.setenv("FIXTURES_DIR", str(tmp_path))
    (tmp_path / "companies.txt").write_text("WK\nNOPE\n")
    monkeypatch.setattr(
        "scripts.fetch_fixtures.build_client",
        lambda _settings: sec_client(sec(), FakeClock()),
    )
    assert main([]) == 1
    assert "NOPE" in capsys.readouterr().err
