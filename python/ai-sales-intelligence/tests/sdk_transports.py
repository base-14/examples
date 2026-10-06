"""Real Anthropic and OpenAI SDK clients that answer from a list of canned responses.

The GenAI instrumentations wrap the SDKs' own methods, so a mocked SDK class would
produce no spans. These helpers keep the real SDK and replace only its HTTP transport.
Each response is either a dict, sent as a 200 JSON body, or an int, sent as that
status with an error body.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from unittest.mock import patch

import anthropic
import httpx
import httpx2
import openai


Response = dict[str, Any] | int


def anthropic_message(mock: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": mock["response_id"],
        "type": "message",
        "role": "assistant",
        "model": mock["model"],
        "content": [{"type": "text", "text": mock["content"]}],
        "stop_reason": mock["finish_reason"],
        "stop_sequence": None,
        "usage": {"input_tokens": mock["input_tokens"], "output_tokens": mock["output_tokens"]},
    }


def openai_completion(mock: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": mock["response_id"],
        "object": "chat.completion",
        "created": 1,
        "model": mock["model"],
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": mock["content"]},
                "finish_reason": mock["finish_reason"],
            }
        ],
        "usage": {
            "prompt_tokens": mock["input_tokens"],
            "completion_tokens": mock["output_tokens"],
            "total_tokens": mock["input_tokens"] + mock["output_tokens"],
        },
    }


def _next_body(responses: list[Response]) -> tuple[int, dict[str, Any]]:
    response = responses.pop(0)
    if isinstance(response, int):
        return response, {"error": {"type": "api_error", "message": f"status {response}"}}
    return 200, response


@contextmanager
def anthropic_responses(responses: list[Response]) -> Iterator[None]:
    """`anthropic.AsyncAnthropic` answers from `responses`, one per request."""
    real = anthropic.AsyncAnthropic

    def handler(request: httpx.Request) -> httpx.Response:
        status, body = _next_body(responses)
        return httpx.Response(status, json=body)

    def client(**kwargs: Any) -> anthropic.AsyncAnthropic:
        transport = httpx.MockTransport(handler)
        return real(**kwargs, http_client=httpx.AsyncClient(transport=transport))

    with patch("anthropic.AsyncAnthropic", side_effect=client):
        yield


@contextmanager
def openai_responses(responses: list[Response]) -> Iterator[None]:
    """`openai.AsyncOpenAI` answers from `responses`, one per request."""
    real = openai.AsyncOpenAI

    def handler(request: httpx2.Request) -> httpx2.Response:
        status, body = _next_body(responses)
        return httpx2.Response(status, json=body)

    def client(**kwargs: Any) -> openai.AsyncOpenAI:
        transport = httpx2.MockTransport(handler)
        return real(**kwargs, http_client=httpx2.AsyncClient(transport=transport))

    with patch("openai.AsyncOpenAI", side_effect=client):
        yield
