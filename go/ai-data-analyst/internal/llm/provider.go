package llm

import (
	"context"
	"fmt"
	"net/url"
	"strconv"

	"ai-data-analyst/internal/config"
)

type GenerateRequest struct {
	Model       string
	System      string
	Prompt      string
	Temperature float64
	MaxTokens   int
	Stage       string
}

type GenerateResponse struct {
	Content      string
	Model        string
	ResponseID   string
	InputTokens  int
	OutputTokens int
	CostUSD      float64
	FinishReason string
}

type Provider interface {
	Generate(ctx context.Context, req GenerateRequest) (*GenerateResponse, error)
	Name() string
	ServerAddress() string
	ServerPort() int
}

// ProviderSemconvNames maps the configuration key that selects a provider to
// the value gen_ai.provider.name carries in telemetry. Gemini is selected with
// the key google and reported as gcp.gemini.
var ProviderSemconvNames = map[string]string{
	"anthropic": "anthropic",
	"openai":    "openai",
	"google":    "gcp.gemini",
	"ollama":    "ollama",
}

func SemconvProviderName(configKey string) string {
	if name, ok := ProviderSemconvNames[configKey]; ok {
		return name
	}
	return configKey
}

func NewProvider(name string, cfg *config.Config) (Provider, error) {
	switch name {
	case "ollama":
		return NewOllamaProvider(cfg.OllamaBaseURL), nil
	case "openai":
		return NewOpenAIProvider(cfg.OpenAIAPIKey), nil
	case "google":
		return NewGoogleProvider(cfg.GoogleAPIKey), nil
	case "anthropic":
		return NewAnthropicProvider(cfg.AnthropicAPIKey), nil
	default:
		return nil, fmt.Errorf("unknown provider %q", name)
	}
}

const (
	defaultOllamaHost = "localhost"
	defaultOllamaPort = 11434
)

func parseServerURL(rawURL string, defaultHost string, defaultPort int) (string, int) {
	u, err := url.Parse(rawURL)
	if err != nil || u.Hostname() == "" {
		return defaultHost, defaultPort
	}
	port := defaultPort
	if p, err := strconv.Atoi(u.Port()); err == nil {
		port = p
	}
	return u.Hostname(), port
}
