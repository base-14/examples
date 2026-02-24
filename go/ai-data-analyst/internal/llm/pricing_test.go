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

func TestProviderPorts(t *testing.T) {
	assert.Equal(t, 443, ProviderPorts["openai"])
	assert.Equal(t, 443, ProviderPorts["anthropic"])
	assert.Equal(t, 11434, ProviderPorts["ollama"])
}
