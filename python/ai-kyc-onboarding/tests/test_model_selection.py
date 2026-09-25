"""The local Ollama model `build_ollama_model` builds, its request settings and profile, and the
GenAI attributes its chat spans carry."""

import json
from collections.abc import AsyncIterator
from functools import partial
from typing import Any

import httpx2
import pytest
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from pydantic_ai import Agent
from pydantic_ai.models.instrumented import InstrumentationSettings, instrument_model
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.profiles.openai import OpenAIJsonSchemaTransformer
from pydantic_ai.providers.ollama import OllamaProvider

from kyc_onboarding.agents.extraction import MAX_TOKENS, TEMPERATURE, build_ollama_model
from kyc_onboarding.agents.faults import StaticFaultRegistry


OLLAMA_BASE_URL = "http://localhost:11434"
MODEL_NAME = "gemma4:e2b"


def _chat_model(model: object) -> OpenAIChatModel:
    wrapped = getattr(model, "wrapped", None)
    assert isinstance(wrapped, OpenAIChatModel)
    return wrapped


def _base_url(model: object) -> str:
    return _chat_model(model).base_url.rstrip("/")


def test_builds_against_local_ollama() -> None:
    model = build_ollama_model(OLLAMA_BASE_URL, MODEL_NAME, StaticFaultRegistry())

    assert _base_url(model) == f"{OLLAMA_BASE_URL}/v1"
    assert isinstance(_chat_model(model)._provider, OllamaProvider)
    assert _chat_model(model).system == "ollama"


def test_the_request_settings_and_profile() -> None:
    chat_model = _chat_model(build_ollama_model(OLLAMA_BASE_URL, MODEL_NAME, StaticFaultRegistry()))

    assert chat_model.settings == {
        "openai_reasoning_effort": "none",
        "temperature": TEMPERATURE,
        "max_tokens": MAX_TOKENS,
    }
    assert chat_model.profile.get("supports_json_object_output") is False


def test_the_local_path_sends_the_cap_as_max_tokens() -> None:
    """Ollama 0.34 ignores `max_completion_tokens` and honours `max_tokens`."""
    local = _chat_model(build_ollama_model(OLLAMA_BASE_URL, MODEL_NAME, StaticFaultRegistry()))

    assert local.profile.get("openai_chat_supports_max_completion_tokens") is False


@pytest.mark.parametrize("model_name", ["gemma4:e2b", "qwen3.5:9B"])
def test_the_local_path_keeps_the_openai_schema_transformer(model_name: str) -> None:
    local = _chat_model(build_ollama_model(OLLAMA_BASE_URL, model_name, StaticFaultRegistry()))

    assert local.profile.get("json_schema_transformer") is OpenAIJsonSchemaTransformer


def _chat_completion(bodies: list[dict[str, Any]], request: httpx2.Request) -> httpx2.Response:
    body = json.loads(request.content)
    bodies.append(body)
    return httpx2.Response(
        200,
        json={
            "id": "chatcmpl-1",
            "object": "chat.completion",
            "created": 0,
            "model": body["model"],
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": "done"},
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12},
        },
    )


@pytest.fixture
async def ollama_request_bodies(
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[list[dict[str, Any]]]:
    """The request bodies a mocked Ollama receives from `build_ollama_model`'s local path."""
    bodies: list[dict[str, Any]] = []
    transport = httpx2.MockTransport(partial(_chat_completion, bodies))
    async with httpx2.AsyncClient(transport=transport) as http_client:
        monkeypatch.setattr(
            "kyc_onboarding.agents.extraction.OllamaProvider",
            partial(OllamaProvider, http_client=http_client),
        )
        yield bodies


async def test_the_local_chat_span_names_ollama_and_the_request_parameters(
    ollama_request_bodies: list[dict[str, Any]],
) -> None:
    exporter = InMemorySpanExporter()
    provider = TracerProvider(resource=Resource.create({"service.name": "test"}))
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    model = build_ollama_model(OLLAMA_BASE_URL, MODEL_NAME, StaticFaultRegistry())

    await Agent(instrument_model(model, InstrumentationSettings(tracer_provider=provider))).run(
        "hello"
    )

    (chat,) = [span for span in exporter.get_finished_spans() if span.name.startswith("chat ")]
    attributes = dict(chat.attributes or {})
    assert attributes["gen_ai.provider.name"] == "ollama"
    assert attributes["gen_ai.system"] == "ollama"
    assert attributes["gen_ai.request.temperature"] == TEMPERATURE
    assert attributes["gen_ai.request.max_tokens"] == MAX_TOKENS
    (sent,) = ollama_request_bodies
    assert (sent["temperature"], sent["max_tokens"]) == (TEMPERATURE, MAX_TOKENS)
    assert "max_completion_tokens" not in sent
