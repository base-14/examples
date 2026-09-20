package llm

import (
	"testing"

	"ai-data-analyst/internal/config"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestProviderServerAddresses(t *testing.T) {
	tests := []struct {
		name     string
		provider Provider
		address  string
		port     int
	}{
		{"openai", NewOpenAIProvider(""), "api.openai.com", 443},
		{"anthropic", NewAnthropicProvider(""), "api.anthropic.com", 443},
		{"google", NewGoogleProvider(""), "generativelanguage.googleapis.com", 443},
		{"ollama", NewOllamaProvider("http://localhost:11434"), "localhost", 11434},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			assert.Equal(t, tt.name, tt.provider.Name())
			assert.Equal(t, tt.address, tt.provider.ServerAddress())
			assert.Equal(t, tt.port, tt.provider.ServerPort())
		})
	}
}

func TestOllamaServerFromBaseURL(t *testing.T) {
	tests := []struct {
		baseURL string
		address string
		port    int
	}{
		{"http://host.docker.internal:11434", "host.docker.internal", 11434},
		{"http://ollama:9999", "ollama", 9999},
		{"http://localhost", "localhost", 11434},
		{"", "localhost", 11434},
	}

	for _, tt := range tests {
		t.Run(tt.baseURL, func(t *testing.T) {
			p := NewOllamaProvider(tt.baseURL)
			assert.Equal(t, tt.address, p.ServerAddress())
			assert.Equal(t, tt.port, p.ServerPort())
		})
	}
}

func TestSemconvProviderName(t *testing.T) {
	assert.Equal(t, "gcp.gemini", SemconvProviderName("google"))
	assert.Equal(t, "anthropic", SemconvProviderName("anthropic"))
	assert.Equal(t, "openai", SemconvProviderName("openai"))
	assert.Equal(t, "ollama", SemconvProviderName("ollama"))
}

func TestNewProviderBuildsEveryConfiguredProvider(t *testing.T) {
	cfg := &config.Config{OllamaBaseURL: "http://localhost:11434"}

	for _, name := range []string{"ollama", "openai", "google", "anthropic"} {
		p, err := NewProvider(name, cfg)
		require.NoError(t, err)
		assert.Equal(t, name, p.Name())
	}

	_, err := NewProvider("nosuchprovider", cfg)
	assert.Error(t, err)
}
