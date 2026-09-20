"""Tests for LLM client."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sales_intelligence.llm import PRICING, PROVIDER_PORTS, LLMClient, _calculate_cost


class TestCostCalculation:
    def test_claude_sonnet_cost(self):
        cost = _calculate_cost("claude-sonnet-4-20250514", 1000, 500)
        expected = (1000 * 3.0 + 500 * 15.0) / 1_000_000
        assert cost == expected

    def test_gemini_flash_cost(self):
        cost = _calculate_cost("gemini-3-flash-preview", 1000, 500)
        expected = (1000 * 0.50 + 500 * 3.0) / 1_000_000
        assert cost == expected

    def test_openai_gpt4o_cost(self):
        cost = _calculate_cost("gpt-4o", 1000, 500)
        expected = (1000 * 2.50 + 500 * 10.0) / 1_000_000
        assert cost == expected

    def test_unknown_model_zero_cost(self):
        cost = _calculate_cost("unknown-model", 1000, 500)
        assert cost == 0.0


class TestProviderPorts:
    def test_ollama_port_is_11434(self):
        assert PROVIDER_PORTS["ollama"] == 11434

    def test_cloud_providers_use_443(self):
        assert PROVIDER_PORTS["anthropic"] == 443
        assert PROVIDER_PORTS["google"] == 443
        assert PROVIDER_PORTS["openai"] == 443


class TestOllamaProvider:
    async def test_generate_returns_content(self):
        """OllamaProvider generates via OpenAI-compatible endpoint."""
        from sales_intelligence.llm import OllamaProvider

        with patch("openai.AsyncOpenAI") as mock_cls:
            mock_response = MagicMock()
            mock_response.choices = [
                MagicMock(
                    message=MagicMock(content="Ollama says hi"),
                    finish_reason="stop",
                )
            ]
            mock_response.usage = MagicMock(prompt_tokens=8, completion_tokens=4)
            mock_response.model = "qwen3.5:9B"
            mock_response.id = "ollama-123"
            mock_cls.return_value.chat.completions.create = AsyncMock(return_value=mock_response)

            provider = OllamaProvider(api_key="", base_url="http://localhost:11434")
            result = await provider.generate(
                model="qwen3.5:9B",
                system="You help.",
                prompt="Hello",
                temperature=0.5,
                max_tokens=256,
            )

        assert result.content == "Ollama says hi"
        assert result.input_tokens == 8
        assert result.output_tokens == 4
        assert result.model == "qwen3.5:9B"

    def test_factory_creates_ollama_provider(self):
        """_create_provider returns OllamaProvider for 'ollama'."""
        from sales_intelligence.llm import OllamaProvider, _create_provider

        with patch("openai.AsyncOpenAI"):
            provider = _create_provider("ollama", api_key="", base_url="http://localhost:11434")
        assert isinstance(provider, OllamaProvider)


class TestLLMClient:
    @pytest.fixture
    def mock_settings(self):
        with patch("sales_intelligence.llm.get_settings") as mock:
            settings = MagicMock()
            settings.llm_provider = "anthropic"
            settings.llm_model_capable = "claude-sonnet-4-6"
            settings.llm_model_fast = "claude-haiku-4-5-20251001"
            settings.fallback_provider = "google"
            settings.fallback_model = "gemini-2.5-flash"
            settings.default_temperature = 0.7
            settings.default_max_tokens = 1024
            settings.anthropic_api_key = "test-key"
            settings.google_api_key = "test-key"
            settings.openai_api_key = "test-key"
            settings.ollama_base_url = "http://localhost:11434"
            settings.otel_instrumentation_genai_capture_message_content = False
            mock.return_value = settings
            yield settings

    @pytest.fixture
    def mock_anthropic(self):
        with patch("anthropic.AsyncAnthropic") as mock:
            yield mock

    @pytest.fixture
    def mock_gemini(self):
        with patch("google.genai.Client") as mock:
            yield mock

    def test_client_exposes_model_capable_and_fast(self, mock_settings):
        client = LLMClient()
        assert client.model_capable == "claude-sonnet-4-6"
        assert client.model_fast == "claude-haiku-4-5-20251001"

    async def test_generate_anthropic(self, mock_settings, mock_anthropic, mock_gemini):
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Hello world")]
        mock_response.usage = MagicMock(input_tokens=10, output_tokens=5)
        mock_response.model = "claude-sonnet-4-6"
        mock_response.id = "msg_123"
        mock_response.stop_reason = "end_turn"

        mock_anthropic.return_value.messages.create = AsyncMock(return_value=mock_response)

        client = LLMClient()
        result = await client.generate(prompt="Say hello")

        assert result == "Hello world"
        mock_anthropic.return_value.messages.create.assert_called_once()

    async def test_generate_gemini(self, mock_settings, mock_anthropic, mock_gemini):
        mock_response = MagicMock()
        mock_response.text = "Hello from Gemini"
        mock_response.usage_metadata = MagicMock(
            prompt_token_count=10,
            candidates_token_count=5,
        )
        mock_response.candidates = [MagicMock(finish_reason="STOP")]

        mock_gemini.return_value.aio.models.generate_content = AsyncMock(return_value=mock_response)

        client = LLMClient()
        result = await client.generate(
            prompt="Say hello", provider="google", model="gemini-2.5-flash"
        )

        assert result == "Hello from Gemini"
        mock_gemini.return_value.aio.models.generate_content.assert_called_once()

    async def test_gemini_span_reports_the_semconv_provider_name(
        self, mock_settings, mock_anthropic, mock_gemini, span_exporter
    ):
        """LLM_PROVIDER=google is reported as gen_ai.provider.name=gcp.gemini."""
        mock_response = MagicMock()
        mock_response.text = "Hello from Gemini"
        mock_response.usage_metadata = MagicMock(
            prompt_token_count=10,
            candidates_token_count=5,
        )
        mock_response.candidates = [MagicMock(finish_reason="STOP")]

        mock_gemini.return_value.aio.models.generate_content = AsyncMock(return_value=mock_response)

        client = LLMClient()
        await client.generate(prompt="Say hello", provider="google", model="gemini-2.5-flash")

        span = span_exporter.get_finished_spans()[-1]
        assert span.name == "chat gemini-2.5-flash"
        assert span.attributes["gen_ai.provider.name"] == "gcp.gemini"
        assert span.attributes["server.address"] == "generativelanguage.googleapis.com"
        assert span.attributes["server.port"] == 443

    async def test_fallback_on_error(self, mock_settings, mock_anthropic, mock_gemini):
        mock_anthropic.return_value.messages.create = AsyncMock(side_effect=Exception("API error"))

        mock_gemini_response = MagicMock()
        mock_gemini_response.text = "Fallback response"
        mock_gemini_response.usage_metadata = MagicMock(
            prompt_token_count=10,
            candidates_token_count=5,
        )
        mock_gemini_response.candidates = [MagicMock(finish_reason="STOP")]
        mock_gemini.return_value.aio.models.generate_content = AsyncMock(
            return_value=mock_gemini_response
        )

        client = LLMClient()
        result = await client.generate(prompt="Say hello", use_fallback=True)

        assert result == "Fallback response"

    async def test_no_fallback_reraises_the_provider_error(
        self, mock_settings, mock_anthropic, mock_gemini
    ):
        """Retries reraise the provider's own error, not tenacity's RetryError."""
        mock_anthropic.return_value.messages.create = AsyncMock(side_effect=Exception("API error"))

        client = LLMClient()

        with pytest.raises(Exception, match="API error"):
            await client.generate(prompt="Say hello", use_fallback=False)

    async def test_agent_name_and_campaign_on_span(
        self, mock_settings, mock_anthropic, mock_gemini, span_exporter
    ):
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Response")]
        mock_response.usage = MagicMock(input_tokens=10, output_tokens=5)
        mock_response.model = "claude-sonnet-4-6"
        mock_response.id = "msg_123"
        mock_response.stop_reason = "end_turn"

        mock_anthropic.return_value.messages.create = AsyncMock(return_value=mock_response)

        client = LLMClient()
        result = await client.generate(
            prompt="Test",
            agent_name="enrich",
            campaign_id="campaign-123",
        )

        assert result == "Response"

        span = next(
            s for s in span_exporter.get_finished_spans() if s.name == "chat claude-sonnet-4-6"
        )
        assert span.attributes["gen_ai.agent.name"] == "enrich"
        assert span.attributes["base14.campaign_id"] == "campaign-123"


class TestContentCapture:
    @pytest.fixture
    def mock_settings(self, request):
        with patch("sales_intelligence.llm.get_settings") as mock:
            settings = MagicMock()
            settings.llm_provider = "anthropic"
            settings.llm_model_capable = "claude-sonnet-4-6"
            settings.llm_model_fast = "claude-sonnet-4-6"
            settings.fallback_provider = "anthropic"
            settings.fallback_model = "claude-sonnet-4-6"
            settings.default_temperature = 0.7
            settings.default_max_tokens = 1024
            settings.anthropic_api_key = "test-key"
            settings.ollama_base_url = "http://localhost:11434"
            settings.otel_instrumentation_genai_capture_message_content = request.param
            mock.return_value = settings
            yield settings

    @pytest.fixture
    def anthropic_client(self):
        with patch("anthropic.AsyncAnthropic") as mock:
            response = MagicMock()
            response.content = [MagicMock(text="Reach Dana on dana@example.com")]
            response.usage = MagicMock(input_tokens=10, output_tokens=5)
            response.model = "claude-sonnet-4-6"
            response.id = "msg_123"
            response.stop_reason = "end_turn"
            mock.return_value.messages.create = AsyncMock(return_value=response)
            yield mock

    @pytest.mark.parametrize("mock_settings", [False], indirect=True)
    async def test_no_event_when_capture_is_off(
        self, mock_settings, anthropic_client, span_exporter
    ):
        await LLMClient().generate(prompt="Email alex@example.com", system="Be brief.")

        span = _chat_span(span_exporter)
        assert [e.name for e in span.events] == []

    @pytest.mark.parametrize("mock_settings", [True], indirect=True)
    async def test_event_content_is_scrubbed(self, mock_settings, anthropic_client, span_exporter):
        await LLMClient().generate(prompt="Email alex@example.com", system="Be brief.")

        span = _chat_span(span_exporter)
        event = span.events[0]

        assert event.name == "gen_ai.client.inference.operation.details"
        assert event.attributes["gen_ai.input.messages"] == "Email [EMAIL]"
        assert event.attributes["gen_ai.output.messages"] == "Reach Dana on [EMAIL]"
        assert event.attributes["gen_ai.system_instructions"] == "Be brief."

    @pytest.mark.parametrize("mock_settings", [True], indirect=True)
    async def test_system_instructions_omitted_when_empty(
        self, mock_settings, anthropic_client, span_exporter
    ):
        await LLMClient().generate(prompt="Hello", system="")

        span = _chat_span(span_exporter)
        assert "gen_ai.system_instructions" not in span.events[0].attributes

    @pytest.mark.parametrize("mock_settings", [True], indirect=True)
    async def test_content_is_truncated(self, mock_settings, anthropic_client, span_exporter):
        await LLMClient().generate(prompt="x" * 2000, system="y" * 800)

        event = _chat_span(span_exporter).events[0]
        assert len(event.attributes["gen_ai.input.messages"]) == 1000
        assert len(event.attributes["gen_ai.system_instructions"]) == 500


def _chat_span(span_exporter):
    return next(s for s in span_exporter.get_finished_spans() if s.name == "chat claude-sonnet-4-6")


def test_pricing_loaded_from_shared_json() -> None:
    """PRICING dict is loaded from _shared/pricing.json, not an inline dict.

    gpt-4.1 is in _shared/pricing.json but NOT in the old inline PRICING dict.
    If PRICING is still inline, this test fails (KeyError or zero cost).
    """
    assert "gpt-4.1" in PRICING, (
        "gpt-4.1 not found in PRICING - pricing may still be inline dict, not loaded from _shared/pricing.json"
    )
    assert PRICING["gpt-4.1"]["input"] == pytest.approx(2.0)
    assert PRICING["gpt-4.1"]["output"] == pytest.approx(8.0)

    cost = _calculate_cost("gpt-4.1", 1_000_000, 0)
    assert cost == pytest.approx(2.0)
