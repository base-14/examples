package config

import (
	"fmt"
	"os"
	"time"
)

type Config struct {
	Port        string
	Environment string

	DatabaseURL string

	TemporalHost      string
	TemporalTaskQueue string

	JWTSecret    string
	JWTExpiresIn time.Duration

	OTelServiceName string
	OTelEndpoint    string
}

func Load() (*Config, error) {
	cfg := &Config{
		Port:              getEnv("PORT", "8080"),
		Environment:       getEnv("ENVIRONMENT", "development"),
		DatabaseURL:       getEnv("DATABASE_URL", ""),
		TemporalHost:      getEnv("TEMPORAL_HOST", "localhost:7233"),
		TemporalTaskQueue: getEnv("TEMPORAL_TASK_QUEUE", "order-fulfillment"),
		JWTSecret:         getEnv("JWT_SECRET", ""),
		OTelServiceName:   getEnv("OTEL_SERVICE_NAME", "go-temporal-postgres-api"),
		OTelEndpoint:      getEnv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318"),
	}

	expiresIn := getEnv("JWT_EXPIRES_IN", "168h")
	duration, err := time.ParseDuration(expiresIn)
	if err != nil {
		return nil, fmt.Errorf("invalid JWT_EXPIRES_IN: %w", err)
	}
	cfg.JWTExpiresIn = duration

	if err := cfg.validate(); err != nil {
		return nil, err
	}

	return cfg, nil
}

func (c *Config) validate() error {
	if c.DatabaseURL == "" {
		return fmt.Errorf("DATABASE_URL is required")
	}
	return nil
}

func (c *Config) IsDevelopment() bool {
	return c.Environment == "development"
}

func getEnv(key, fallback string) string {
	if value, ok := os.LookupEnv(key); ok {
		return value
	}
	return fallback
}
