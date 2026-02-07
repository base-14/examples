import pytest

from content_quality.services.prompts import PromptPair, load_prompt


def test_load_review_v1_returns_prompt_pair() -> None:
    result = load_prompt.__wrapped__("review_v1")
    assert isinstance(result, PromptPair)
    assert "{content}" in result.user
    assert result.system


def test_all_prompts_load_successfully() -> None:
    for name in ("review_v1", "review_v2", "improve_v1", "score_v1"):
        result = load_prompt.__wrapped__(name)
        assert isinstance(result, PromptPair)
        assert result.system
        assert result.user


def test_nonexistent_prompt_raises_file_not_found() -> None:
    with pytest.raises(FileNotFoundError):
        load_prompt.__wrapped__("nonexistent_prompt")


def test_double_braces_converted_to_single() -> None:
    result = load_prompt.__wrapped__("review_v1")
    assert "{{content}}" not in result.user
    assert "{content}" in result.user
    assert "{{content}}" not in result.system
