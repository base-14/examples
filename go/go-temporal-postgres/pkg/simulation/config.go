package simulation

import (
	"os"
	"strconv"
)

type Config struct {
	FailureRate  float64
	MinLatencyMs int
	MaxLatencyMs int
	Enabled      bool
}

func LoadConfig(prefix string) Config {
	return Config{
		FailureRate:  getEnvFloat(prefix+"_FAILURE_RATE", 0.0),
		MinLatencyMs: getEnvInt(prefix+"_LATENCY_MIN_MS", 0),
		MaxLatencyMs: getEnvInt(prefix+"_LATENCY_MAX_MS", 0),
		Enabled:      getEnvBool(prefix+"_SIMULATION_ENABLED", true),
	}
}

func getEnvFloat(key string, defaultVal float64) float64 {
	if val := os.Getenv(key); val != "" {
		if f, err := strconv.ParseFloat(val, 64); err == nil {
			return f
		}
	}
	return defaultVal
}

func getEnvInt(key string, defaultVal int) int {
	if val := os.Getenv(key); val != "" {
		if i, err := strconv.Atoi(val); err == nil {
			return i
		}
	}
	return defaultVal
}

func getEnvBool(key string, defaultVal bool) bool {
	if val := os.Getenv(key); val != "" {
		if b, err := strconv.ParseBool(val); err == nil {
			return b
		}
	}
	return defaultVal
}
