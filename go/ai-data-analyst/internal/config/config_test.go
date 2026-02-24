package config

import (
	"os"
	"testing"

	"github.com/stretchr/testify/assert"
)

func TestLoadDefaults(t *testing.T) {
	os.Clearenv()
	cfg := Load()

	assert.Equal(t, "8080", cfg.Port)
	assert.Equal(t, "openai", cfg.LLMProvider)
	assert.Equal(t, "gpt-4.1", cfg.LLMModelCapable)
	assert.Equal(t, "gpt-4.1-mini", cfg.LLMModelFast)
	assert.Equal(t, "anthropic", cfg.FallbackProvider)
	assert.Equal(t, "claude-haiku-4-5-20251001", cfg.FallbackModel)
	assert.Equal(t, "http://localhost:11434", cfg.OllamaBaseURL)
	assert.Equal(t, "ai-data-analyst", cfg.OTelServiceName)
	assert.Equal(t, "http://localhost:4318", cfg.OTelEndpoint)
	assert.Equal(t, "development", cfg.ScoutEnvironment)
	assert.InDelta(t, 0.1, cfg.DefaultTemperature, 0.001)
	assert.Equal(t, 1024, cfg.DefaultMaxTokens)
}

func TestLoadFromEnv(t *testing.T) {
	t.Setenv("APP_PORT", "9090")
	t.Setenv("LLM_PROVIDER", "ollama")
	t.Setenv("LLM_MODEL_CAPABLE", "llama3")
	t.Setenv("DEFAULT_TEMPERATURE", "0.5")
	t.Setenv("DEFAULT_MAX_TOKENS", "2048")
	t.Setenv("OPENAI_API_KEY", "sk-test")

	cfg := Load()

	assert.Equal(t, "9090", cfg.Port)
	assert.Equal(t, "ollama", cfg.LLMProvider)
	assert.Equal(t, "llama3", cfg.LLMModelCapable)
	assert.InDelta(t, 0.5, cfg.DefaultTemperature, 0.001)
	assert.Equal(t, 2048, cfg.DefaultMaxTokens)
	assert.Equal(t, "sk-test", cfg.OpenAIAPIKey)
}

func TestInvalidNumericFallsBackToDefault(t *testing.T) {
	t.Setenv("DEFAULT_TEMPERATURE", "not-a-number")
	t.Setenv("DEFAULT_MAX_TOKENS", "abc")

	cfg := Load()

	assert.InDelta(t, 0.1, cfg.DefaultTemperature, 0.001)
	assert.Equal(t, 1024, cfg.DefaultMaxTokens)
}
