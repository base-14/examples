package llm

import (
	"testing"

	"github.com/stretchr/testify/assert"
)

func TestPricingLoaded(t *testing.T) {
	assert.Greater(t, len(Pricing), 10, "pricing.json should have >10 models")
	assert.Equal(t, 2.0, Pricing["gpt-4.1"].Input, "gpt-4.1 input price")
	assert.Equal(t, 8.0, Pricing["gpt-4.1"].Output, "gpt-4.1 output price")
	assert.Equal(t, "openai", Pricing["gpt-4.1"].Provider)
}

func TestCalculateCost(t *testing.T) {
	cost := CalculateCost("gpt-4.1", 2500, 300)
	expected := (2500.0*2.0 + 300.0*8.0) / 1_000_000
	assert.InDelta(t, expected, cost, 0.0001)
}

func TestCalculateCostUnknownModel(t *testing.T) {
	cost := CalculateCost("nonexistent-model", 1000, 500)
	assert.Equal(t, 0.0, cost)
}

func TestCalculateCostDatedSnapshot(t *testing.T) {
	openai := CalculateCost("gpt-4.1-2025-04-14", 1000, 500)
	assert.Greater(t, openai, 0.0, "dated OpenAI snapshot must resolve a non-zero cost")
	assert.InDelta(t, CalculateCost("gpt-4.1", 1000, 500), openai, 0.0001)

	anthropic := CalculateCost("claude-haiku-4-5-20251001", 1000, 500)
	assert.Greater(t, anthropic, 0.0, "dated Anthropic snapshot must resolve a non-zero cost")
	assert.InDelta(t, CalculateCost("claude-haiku-4.5", 1000, 500), anthropic, 0.0001)
}

func TestProviderPorts(t *testing.T) {
	assert.Equal(t, 443, ProviderPorts["openai"])
	assert.Equal(t, 443, ProviderPorts["anthropic"])
	assert.Equal(t, 11434, ProviderPorts["ollama"])
}
