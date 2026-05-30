package llm

import (
	"encoding/json"
	"log"
	"os"
	"path/filepath"
	"regexp"
	"runtime"
)

type PriceEntry struct {
	Provider string  `json:"provider"`
	Input    float64 `json:"input"`
	Output   float64 `json:"output"`
}

var Pricing map[string]PriceEntry

func init() {
	Pricing = make(map[string]PriceEntry)

	paths := []string{
		"/_shared/pricing.json",
		os.Getenv("PRICING_JSON_PATH"),
		findRelativePricing(),
	}

	for _, p := range paths {
		if p == "" {
			continue
		}
		data, err := os.ReadFile(p)
		if err != nil {
			continue
		}
		var raw struct {
			Models map[string]PriceEntry `json:"models"`
		}
		if err := json.Unmarshal(data, &raw); err != nil {
			continue
		}
		if len(raw.Models) > 0 {
			Pricing = raw.Models
			return
		}
	}
	log.Println("WARNING: pricing.json not found, costs will be $0.00")
}

func findRelativePricing() string {
	_, filename, _, ok := runtime.Caller(0)
	if !ok {
		return ""
	}
	// internal/llm/pricing.go -> repo root -> ../../../../_shared
	dir := filepath.Dir(filename)
	return filepath.Join(dir, "..", "..", "..", "..", "_shared", "pricing.json")
}

// normalizeModel maps a provider's dated snapshot ("gpt-4.1-2025-04-14",
// "claude-haiku-4-5-20251001") back to the canonical pricing.json key.
var (
	dateSuffix       = regexp.MustCompile(`-\d{4}-\d{2}-\d{2}$|-\d{8}$`)
	anthropicVersion = regexp.MustCompile(`-(\d+)-(\d+)$`)
)

func normalizeModel(model string) string {
	m := dateSuffix.ReplaceAllString(model, "")
	return anthropicVersion.ReplaceAllString(m, "-$1.$2")
}

func CalculateCost(model string, inputTokens, outputTokens int) float64 {
	entry, ok := Pricing[model]
	if !ok {
		entry, ok = Pricing[normalizeModel(model)]
	}
	if !ok {
		return 0.0
	}
	return (float64(inputTokens) * entry.Input / 1_000_000) +
		(float64(outputTokens) * entry.Output / 1_000_000)
}

var ProviderServers = map[string]string{
	"openai":    "api.openai.com",
	"anthropic": "api.anthropic.com",
	"google":    "generativelanguage.googleapis.com",
	"ollama":    "localhost",
}

var ProviderPorts = map[string]int{
	"openai":    443,
	"anthropic": 443,
	"google":    443,
	"ollama":    11434,
}
