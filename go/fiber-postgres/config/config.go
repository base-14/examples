package config

import (
	"os"
	"time"
)

type Config struct {
	Port        string
	Environment string
	DatabaseURL string
	JWTSecret   string
	JWTExpiry   time.Duration
	OTelConfig  OTelConfig
}

type OTelConfig struct {
	ServiceName  string
	OTLPEndpoint string
}

func Load() *Config {
	return &Config{
		Port:        getEnv("PORT", "8080"),
		Environment: getEnv("ENVIRONMENT", "development"),
		DatabaseURL: getEnv("DATABASE_URL", "postgres://postgres:postgres@localhost:5432/gofiber?sslmode=disable"),
		JWTSecret:   getEnv("JWT_SECRET", "your-super-secret-jwt-key-change-in-production"),
		JWTExpiry:   parseDuration(getEnv("JWT_EXPIRES_IN", "168h")),
		OTelConfig: OTelConfig{
			ServiceName:  getEnv("OTEL_SERVICE_NAME", "go-fiber-postgres-api"),
			OTLPEndpoint: getEnv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318"),
		},
	}
}

func getEnv(key, defaultValue string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return defaultValue
}

func parseDuration(s string) time.Duration {
	d, err := time.ParseDuration(s)
	if err != nil {
		return 168 * time.Hour
	}
	return d
}
