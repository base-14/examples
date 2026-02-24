package pipeline

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"runtime"
	"strings"

	"ai-data-analyst/internal/llm"

	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/codes"
	"go.opentelemetry.io/otel/trace"
)

type GenerateResult struct {
	SQL          string   `json:"sql"`
	Explanation  string   `json:"explanation"`
	TablesUsed   []string `json:"tables_used"`
	Confidence   float64  `json:"confidence"`
	InputTokens  int      `json:"-"`
	OutputTokens int      `json:"-"`
	CostUSD      float64  `json:"-"`
}

var schemaContext string

func init() {
	paths := []string{
		"/app/data/schema-context.txt",
		findSchemaContext(),
	}
	for _, p := range paths {
		if p == "" {
			continue
		}
		data, err := os.ReadFile(p)
		if err != nil {
			continue
		}
		schemaContext = string(data)
		return
	}
	schemaContext = "You are a SQL expert. Generate PostgreSQL queries."
}

func findSchemaContext() string {
	_, filename, _, ok := runtime.Caller(0)
	if !ok {
		return ""
	}
	dir := filepath.Dir(filename)
	return filepath.Join(dir, "..", "..", "data", "schema-context.txt")
}

func Generate(ctx context.Context, tracer trace.Tracer, client *llm.Client, question string, parsed *ParseResult, model string, temperature float64, maxTokens int) (*GenerateResult, error) {
	ctx, span := tracer.Start(ctx, "pipeline_stage generate")
	defer span.End()

	span.SetAttributes(attribute.String("nlsql.stage", "generate"))

	prompt := buildGeneratePrompt(question, parsed)

	resp, err := client.Generate(ctx, llm.GenerateRequest{
		Model:       model,
		System:      schemaContext,
		Prompt:      prompt,
		Temperature: temperature,
		MaxTokens:   maxTokens,
		Stage:       "generate",
	})
	if err != nil {
		span.SetStatus(codes.Error, err.Error())
		return nil, fmt.Errorf("SQL generation failed: %w", err)
	}

	result := parseGenerateResponse(resp.Content)
	result.InputTokens = resp.InputTokens
	result.OutputTokens = resp.OutputTokens
	result.CostUSD = resp.CostUSD

	span.SetAttributes(
		attribute.Float64("nlsql.confidence", result.Confidence),
		attribute.Int("nlsql.sql_length", len(result.SQL)),
	)

	return result, nil
}

func buildGeneratePrompt(question string, parsed *ParseResult) string {
	var sb strings.Builder
	sb.WriteString("Question: " + question + "\n\n")

	if len(parsed.Indicators) > 0 {
		sb.WriteString("Detected indicators: " + strings.Join(parsed.Indicators, ", ") + "\n")
	}
	if len(parsed.Countries) > 0 {
		sb.WriteString("Detected countries: " + strings.Join(parsed.Countries, ", ") + "\n")
	}
	if parsed.TimeRange != nil {
		sb.WriteString(fmt.Sprintf("Time range: %d-%d\n", parsed.TimeRange.StartYear, parsed.TimeRange.EndYear))
	}
	sb.WriteString("Question type: " + parsed.QuestionType + "\n")
	sb.WriteString("\nRespond with a JSON object: {\"sql\": \"...\", \"explanation\": \"...\", \"tables_used\": [...], \"confidence\": 0.0-1.0}")

	return sb.String()
}

var jsonBlockPattern = regexp.MustCompile("(?s)```(?:json)?\\s*(\\{.*?\\})\\s*```")
var jsonObjectPattern = regexp.MustCompile(`(?s)\{[^{}]*"sql"\s*:\s*"[^"]*"[^{}]*\}`)

func parseGenerateResponse(content string) *GenerateResult {
	result := &GenerateResult{Confidence: 0.5}

	// Try JSON block first
	if m := jsonBlockPattern.FindStringSubmatch(content); m != nil {
		if err := json.Unmarshal([]byte(m[1]), result); err == nil && result.SQL != "" {
			return result
		}
	}

	// Try raw JSON
	if err := json.Unmarshal([]byte(content), result); err == nil && result.SQL != "" {
		return result
	}

	// Try finding JSON object in text
	if m := jsonObjectPattern.FindString(content); m != "" {
		if err := json.Unmarshal([]byte(m), result); err == nil && result.SQL != "" {
			return result
		}
	}

	// Fallback: extract SQL from content
	sqlPattern := regexp.MustCompile("(?s)```(?:sql)?\\s*(SELECT.*?)\\s*```")
	if m := sqlPattern.FindStringSubmatch(content); m != nil {
		result.SQL = strings.TrimSpace(m[1])
		result.Explanation = "SQL extracted from response"
		result.Confidence = 0.4
		return result
	}

	// Last resort: use the whole content as SQL
	if strings.Contains(strings.ToUpper(content), "SELECT") {
		result.SQL = strings.TrimSpace(content)
		result.Confidence = 0.3
	}

	return result
}
