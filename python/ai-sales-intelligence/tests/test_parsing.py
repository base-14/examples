"""Tests for sales_intelligence.parsing."""

import json

import pytest

from sales_intelligence.parsing import extract_json


class TestExtractJson:
    def test_plain_json(self):
        result = extract_json('{"name": "Alice", "age": 30}')
        assert result == {"name": "Alice", "age": 30}

    def test_markdown_fenced(self):
        text = '```json\n{"key": "value"}\n```'
        assert extract_json(text) == {"key": "value"}

    def test_markdown_fenced_no_lang(self):
        text = '```\n{"key": "value"}\n```'
        assert extract_json(text) == {"key": "value"}

    def test_json_with_surrounding_text(self):
        text = 'Here is the result:\n{"score": 85}\nThat looks good.'
        assert extract_json(text) == {"score": 85}

    def test_nested_objects(self):
        text = '{"outer": {"inner": {"deep": true}}, "list": [1, 2]}'
        result = extract_json(text)
        assert result["outer"]["inner"]["deep"] is True
        assert result["list"] == [1, 2]

    def test_escaped_quotes_in_strings(self):
        text = r'{"msg": "He said \"hello\""}'
        result = extract_json(text)
        assert result["msg"] == 'He said "hello"'

    def test_trailing_comma_object(self):
        text = '{"a": 1, "b": 2,}'
        result = extract_json(text)
        assert result == {"a": 1, "b": 2}

    def test_trailing_comma_array(self):
        text = '{"items": [1, 2, 3,]}'
        result = extract_json(text)
        assert result == {"items": [1, 2, 3]}

    def test_trailing_comma_nested(self):
        text = '{"a": {"b": 1,}, "c": [2,],}'
        result = extract_json(text)
        assert result == {"a": {"b": 1}, "c": [2]}

    def test_no_json_raises(self):
        with pytest.raises(json.JSONDecodeError, match="No JSON object found"):
            extract_json("no json here")

    def test_unterminated_json_raises(self):
        with pytest.raises(json.JSONDecodeError):
            extract_json('{"key": "value"')

    def test_empty_object(self):
        assert extract_json("{}") == {}

    def test_whitespace_around_json(self):
        text = "  \n  {\"x\": 1}  \n  "
        assert extract_json(text) == {"x": 1}

    def test_braces_inside_strings_ignored(self):
        text = '{"template": "Hello {name}, welcome to {place}"}'
        result = extract_json(text)
        assert result["template"] == "Hello {name}, welcome to {place}"

    def test_backslash_in_string(self):
        text = r'{"path": "C:\\Users\\test"}'
        result = extract_json(text)
        assert result["path"] == "C:\\Users\\test"
