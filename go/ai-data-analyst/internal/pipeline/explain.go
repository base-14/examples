package pipeline

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"

	"ai-data-analyst/internal/llm"

	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/codes"
	"go.opentelemetry.io/otel/trace"
)

type ExplainResult struct {
	Summary      string   `json:"summary"`
	Insights     []string `json:"insights"`
	Caveats      []string `json:"caveats"`
	FollowUps    []string `json:"follow_ups"`
	InputTokens  int      `json:"-"`
	OutputTokens int      `json:"-"`
	CostUSD      float64  `json:"-"`
}

const explainSystemPrompt = `You are a data analyst explaining query results to a non-technical audience.
Given a question, the SQL query used, and the results, provide:
1. A 2-3 sentence summary answering the question
2. Key insights from the data (2-4 bullet points)
3. Any caveats or limitations
4. Suggested follow-up questions (1-3)

Respond with JSON: {"summary": "...", "insights": [...], "caveats": [...], "follow_ups": [...]}`

func Explain(ctx context.Context, tracer trace.Tracer, client *llm.Client, question string, sql string, execResult *ExecuteResult, model string, temperature float64, maxTokens int) (*ExplainResult, error) {
	ctx, span := tracer.Start(ctx, "pipeline_stage explain")
	defer span.End()

	span.SetAttributes(attribute.String("nlsql.stage", "explain"))

	prompt := buildExplainPrompt(question, sql, execResult)

	resp, err := client.Generate(ctx, llm.GenerateRequest{
		Model:       model,
		System:      explainSystemPrompt,
		Prompt:      prompt,
		Temperature: temperature,
		MaxTokens:   maxTokens,
		Stage:       "explain",
	})
	if err != nil {
		span.SetStatus(codes.Error, err.Error())
		return nil, fmt.Errorf("explanation generation failed: %w", err)
	}

	result := parseExplainResponse(resp.Content)
	result.InputTokens = resp.InputTokens
	result.OutputTokens = resp.OutputTokens
	result.CostUSD = resp.CostUSD

	span.SetAttributes(
		attribute.Int("nlsql.summary_length", len(result.Summary)),
		attribute.Int("nlsql.insights_count", len(result.Insights)),
		attribute.Int("nlsql.follow_ups_count", len(result.FollowUps)),
	)

	return result, nil
}

func buildExplainPrompt(question string, sql string, execResult *ExecuteResult) string {
	var sb strings.Builder
	sb.WriteString("Question: " + question + "\n\n")
	sb.WriteString("SQL Query:\n" + sql + "\n\n")

	if execResult.RowCount == 0 {
		sb.WriteString("Results: No data returned (0 rows).\n")
		sb.WriteString("Please explain why there might be no data and suggest how to broaden the query.\n")
		return sb.String()
	}

	sb.WriteString(fmt.Sprintf("Results (%d rows):\n", execResult.RowCount))

	// Format as markdown table
	sb.WriteString("| " + strings.Join(execResult.Columns, " | ") + " |\n")
	sb.WriteString("|" + strings.Repeat(" --- |", len(execResult.Columns)) + "\n")

	maxRows := 20
	if execResult.RowCount < maxRows {
		maxRows = execResult.RowCount
	}
	for i := 0; i < maxRows; i++ {
		row := execResult.Rows[i]
		vals := make([]string, len(row))
		for j, v := range row {
			if v == nil {
				vals[j] = "NULL"
			} else {
				vals[j] = fmt.Sprintf("%v", v)
			}
		}
		sb.WriteString("| " + strings.Join(vals, " | ") + " |\n")
	}
	if execResult.RowCount > maxRows {
		sb.WriteString(fmt.Sprintf("\n... and %d more rows\n", execResult.RowCount-maxRows))
	}

	return sb.String()
}

func parseExplainResponse(content string) *ExplainResult {
	result := &ExplainResult{}

	// Try JSON parse
	if err := json.Unmarshal([]byte(content), result); err == nil && result.Summary != "" {
		return result
	}

	// Try JSON block
	if m := jsonBlockPattern.FindStringSubmatch(content); m != nil {
		if err := json.Unmarshal([]byte(m[1]), result); err == nil && result.Summary != "" {
			return result
		}
	}

	// Fallback: use raw content as summary
	result.Summary = strings.TrimSpace(content)
	if len(result.Summary) > 500 {
		result.Summary = result.Summary[:500]
	}
	return result
}
