"""Tests for LLM client."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sales_intelligence.llm import LLMClient, _calculate_cost


class TestCostCalculation:
    def test_claude_sonnet_cost(self):
        cost = _calculate_cost("claude-sonnet-4-20250514", 1000, 500)
        expected = (1000 * 3.0 + 500 * 15.0) / 1_000_000
        assert cost == expected

    def test_gemini_flash_cost(self):
        cost = _calculate_cost("gemini-3-flash", 1000, 500)
        expected = (1000 * 0.50 + 500 * 3.0) / 1_000_000
        assert cost == expected

    def test_openai_gpt4o_cost(self):
        cost = _calculate_cost("gpt-4o", 1000, 500)
        expected = (1000 * 2.50 + 500 * 10.0) / 1_000_000
        assert cost == expected

    def test_unknown_model_zero_cost(self):
        cost = _calculate_cost("unknown-model", 1000, 500)
        assert cost == 0.0


class TestLLMClient:
    @pytest.fixture
    def mock_settings(self):
        with patch("sales_intelligence.llm.get_settings") as mock:
            settings = MagicMock()
            settings.llm_provider = "anthropic"
            settings.llm_model = "claude-sonnet-4-20250514"
            settings.fallback_provider = "google"
            settings.fallback_model = "gemini-3-flash"
            settings.default_temperature = 0.7
            settings.default_max_tokens = 1024
            settings.anthropic_api_key = "test-key"
            settings.google_api_key = "test-key"
            settings.openai_api_key = "test-key"
            mock.return_value = settings
            yield settings

    @pytest.fixture
    def mock_anthropic(self):
        with patch("anthropic.AsyncAnthropic") as mock:
            yield mock

    @pytest.fixture
    def mock_google(self):
        with patch("google.genai.Client") as mock:
            yield mock

    async def test_generate_anthropic(self, mock_settings, mock_anthropic, mock_google):
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Hello world")]
        mock_response.usage = MagicMock(input_tokens=10, output_tokens=5)
        mock_response.model = "claude-sonnet-4-20250514"
        mock_response.id = "msg_123"
        mock_response.stop_reason = "end_turn"

        mock_anthropic.return_value.messages.create = AsyncMock(return_value=mock_response)

        client = LLMClient()
        result = await client.generate(prompt="Say hello")

        assert result == "Hello world"
        mock_anthropic.return_value.messages.create.assert_called_once()

    async def test_generate_google(self, mock_settings, mock_anthropic, mock_google):
        mock_response = MagicMock()
        mock_response.text = "Hello from Google"
        mock_response.usage_metadata = MagicMock(
            prompt_token_count=10,
            candidates_token_count=5,
        )
        mock_response.candidates = [MagicMock(finish_reason="STOP")]

        mock_google.return_value.aio.models.generate_content = AsyncMock(return_value=mock_response)

        client = LLMClient()
        result = await client.generate(
            prompt="Say hello", provider="google", model="gemini-3-flash"
        )

        assert result == "Hello from Google"
        mock_google.return_value.aio.models.generate_content.assert_called_once()

    async def test_fallback_on_error(self, mock_settings, mock_anthropic, mock_google):
        mock_anthropic.return_value.messages.create = AsyncMock(side_effect=Exception("API error"))

        mock_google_response = MagicMock()
        mock_google_response.text = "Fallback response"
        mock_google_response.usage_metadata = MagicMock(
            prompt_token_count=10,
            candidates_token_count=5,
        )
        mock_google_response.candidates = [MagicMock(finish_reason="STOP")]
        mock_google.return_value.aio.models.generate_content = AsyncMock(
            return_value=mock_google_response
        )

        client = LLMClient()
        result = await client.generate(prompt="Say hello", use_fallback=True)

        assert result == "Fallback response"

    async def test_no_fallback_raises(self, mock_settings, mock_anthropic, mock_google):
        from tenacity import RetryError

        mock_anthropic.return_value.messages.create = AsyncMock(side_effect=Exception("API error"))

        client = LLMClient()

        with pytest.raises(RetryError):
            await client.generate(prompt="Say hello", use_fallback=False)

    async def test_agent_name_passed_to_span(self, mock_settings, mock_anthropic, mock_google):
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Response")]
        mock_response.usage = MagicMock(input_tokens=10, output_tokens=5)
        mock_response.model = "claude-sonnet-4-20250514"
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
