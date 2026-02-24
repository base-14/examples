package config

import (
	"os"
	"strconv"
)

type Config struct {
	Port               string
	DatabaseURL        string
	LLMProvider        string
	LLMModelCapable    string
	LLMModelFast       string
	FallbackProvider   string
	FallbackModel      string
	OllamaBaseURL      string
	OpenAIAPIKey       string
	GoogleAPIKey       string
	AnthropicAPIKey    string
	OTelServiceName    string
	OTelEndpoint       string
	ScoutEnvironment   string
	DefaultTemperature float64
	DefaultMaxTokens   int
}

func Load() *Config {
	return &Config{
		Port:               envOr("APP_PORT", "8080"),
		DatabaseURL:        envOr("DATABASE_URL", "postgres://postgres:postgres@localhost:5432/data_analyst?sslmode=disable"),
		LLMProvider:        envOr("LLM_PROVIDER", "openai"),
		LLMModelCapable:    envOr("LLM_MODEL_CAPABLE", "gpt-4.1"),
		LLMModelFast:       envOr("LLM_MODEL_FAST", "gpt-4.1-mini"),
		FallbackProvider:   envOr("FALLBACK_PROVIDER", "anthropic"),
		FallbackModel:      envOr("FALLBACK_MODEL", "claude-haiku-4-5-20251001"),
		OllamaBaseURL:      envOr("OLLAMA_BASE_URL", "http://localhost:11434"),
		OpenAIAPIKey:       os.Getenv("OPENAI_API_KEY"),
		GoogleAPIKey:       os.Getenv("GOOGLE_API_KEY"),
		AnthropicAPIKey:    os.Getenv("ANTHROPIC_API_KEY"),
		OTelServiceName:    envOr("OTEL_SERVICE_NAME", "ai-data-analyst"),
		OTelEndpoint:       envOr("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318"),
		ScoutEnvironment:   envOr("SCOUT_ENVIRONMENT", "development"),
		DefaultTemperature: envOrFloat("DEFAULT_TEMPERATURE", 0.1),
		DefaultMaxTokens:   envOrInt("DEFAULT_MAX_TOKENS", 1024),
	}
}

func envOr(key, fallback string) string {
	if v, ok := os.LookupEnv(key); ok {
		return v
	}
	return fallback
}

func envOrFloat(key string, fallback float64) float64 {
	if v, ok := os.LookupEnv(key); ok {
		if f, err := strconv.ParseFloat(v, 64); err == nil {
			return f
		}
	}
	return fallback
}

func envOrInt(key string, fallback int) int {
	if v, ok := os.LookupEnv(key); ok {
		if i, err := strconv.Atoi(v); err == nil {
			return i
		}
	}
	return fallback
}
