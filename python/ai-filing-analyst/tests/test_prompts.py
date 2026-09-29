from pathlib import Path

import pytest

from filing_analyst.prompts import load_prompt


PROMPTS = Path(__file__).parents[1] / "prompts"


PROMPT_VERSION = "202609261523"


def _prompt_file(directory: Path, name: str, version: str, text: str) -> None:
    (directory / f"{version}_{name}.yaml").write_text(f"- role: system\n  content: |\n    {text}\n")


def test_a_prompt_version_is_the_timestamp_in_its_filename() -> None:
    analyst = load_prompt(PROMPTS, "analyst", PROMPT_VERSION)
    assert analyst.version == PROMPT_VERSION
    assert "accession" in analyst.system
    with pytest.raises(FileNotFoundError):
        load_prompt(PROMPTS, "analyst", "202001010000")


def test_no_version_loads_the_newest_prompt(tmp_path: Path) -> None:
    _prompt_file(tmp_path, "analyst", "202609260900", "older")
    _prompt_file(tmp_path, "analyst", "202610011200", "newest")
    _prompt_file(tmp_path, "ranking", "202611010000", "another agent")
    newest = load_prompt(tmp_path, "analyst")
    assert (newest.version, newest.system) == ("202610011200", "newest")
    with pytest.raises(FileNotFoundError):
        load_prompt(tmp_path, "missing")


def test_a_version_that_is_not_a_timestamp_is_refused() -> None:
    with pytest.raises(ValueError, match="YYYYMMDDHHMM"):
        load_prompt(PROMPTS, "analyst", "v1")
