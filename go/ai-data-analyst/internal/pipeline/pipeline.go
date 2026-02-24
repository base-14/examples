package pipeline

import (
	"context"
	"fmt"
	"time"

	"ai-data-analyst/internal/config"
	"ai-data-analyst/internal/db"
	"ai-data-analyst/internal/llm"
	"ai-data-analyst/internal/telemetry"

	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/codes"
	"go.opentelemetry.io/otel/trace"
)

type AskResult struct {
	Question     string         `json:"question"`
	SQL          string         `json:"sql"`
	Columns      []string       `json:"columns"`
	Rows         [][]any        `json:"rows"`
	RowCount     int            `json:"row_count"`
	Explanation  *ExplainResult `json:"explanation"`
	Confidence   float64        `json:"confidence"`
	TotalTokens  int            `json:"total_tokens"`
	TotalCostUSD float64        `json:"total_cost_usd"`
	DurationMS   int64          `json:"duration_ms"`
	TraceID      string         `json:"trace_id"`
}

type Pipeline struct {
	LLM     *llm.Client
	DB      db.Querier
	Tracer  trace.Tracer
	Metrics *telemetry.GenAIMetrics
	Config  *config.Config
}

func (p *Pipeline) Ask(ctx context.Context, question string) (*AskResult, error) {
	start := time.Now()

	ctx, span := p.Tracer.Start(ctx, "pipeline ask")
	defer span.End()

	traceID := span.SpanContext().TraceID().String()

	// Stage 1: Parse
	parsed := Parse(ctx, p.Tracer, question)

	// Stage 2: Generate SQL
	genResult, err := Generate(ctx, p.Tracer, p.LLM, question, parsed,
		p.Config.LLMModelCapable, p.Config.DefaultTemperature, p.Config.DefaultMaxTokens)
	if err != nil {
		span.SetStatus(codes.Error, err.Error())
		return nil, fmt.Errorf("generate stage failed: %w", err)
	}

	if genResult.SQL == "" {
		span.SetStatus(codes.Error, "no SQL generated")
		return nil, fmt.Errorf("LLM did not generate SQL for: %s", question)
	}

	// Low confidence check
	if genResult.Confidence < 0.3 {
		return &AskResult{
			Question:   question,
			SQL:        genResult.SQL,
			Confidence: genResult.Confidence,
			DurationMS: time.Since(start).Milliseconds(),
			TraceID:    traceID,
			Explanation: &ExplainResult{
				Summary: "The question is too ambiguous for confident SQL generation. Please provide more detail about what data you're looking for.",
			},
		}, nil
	}

	// Stage 3: Validate SQL
	validated := Validate(ctx, p.Tracer, genResult.SQL)

	if p.Metrics != nil {
		p.Metrics.SQLValid.Add(ctx, 1,
			telemetry.WithBoolAttr("nlsql.valid", validated.Valid),
		)
	}

	if !validated.Valid {
		span.SetAttributes(
			attribute.StringSlice("nlsql.violations", validated.Violations),
		)
		return &AskResult{
			Question:   question,
			SQL:        genResult.SQL,
			Confidence: genResult.Confidence,
			DurationMS: time.Since(start).Milliseconds(),
			TraceID:    traceID,
			Explanation: &ExplainResult{
				Summary: "The generated SQL was rejected by safety validation: " + fmt.Sprintf("%v", validated.Violations),
			},
		}, nil
	}

	// Stage 4: Execute
	execResult, err := Execute(ctx, p.Tracer, p.DB, validated.SafeSQL)
	if err != nil {
		span.SetStatus(codes.Error, err.Error())
		return nil, fmt.Errorf("execute stage failed: %w", err)
	}

	questionTypeAttr := telemetry.WithQuestionType(parsed.QuestionType)

	if p.Metrics != nil {
		p.Metrics.QueryRows.Record(ctx, float64(execResult.RowCount), questionTypeAttr)
		p.Metrics.QueryExecutionTime.Record(ctx, float64(execResult.Duration.Milliseconds()), questionTypeAttr)
		p.Metrics.Confidence.Record(ctx, genResult.Confidence, questionTypeAttr)
	}

	// Stage 5: Explain
	explainResult, err := Explain(ctx, p.Tracer, p.LLM, question, validated.SafeSQL, execResult,
		p.Config.LLMModelFast, 0.3, 512)
	if err != nil {
		span.SetStatus(codes.Error, err.Error())
		return nil, fmt.Errorf("explain stage failed: %w", err)
	}

	duration := time.Since(start)

	totalTokens := genResult.InputTokens + genResult.OutputTokens + explainResult.InputTokens + explainResult.OutputTokens
	totalCost := genResult.CostUSD + explainResult.CostUSD

	result := &AskResult{
		Question:     question,
		SQL:          validated.SafeSQL,
		Columns:      execResult.Columns,
		Rows:         execResult.Rows,
		RowCount:     execResult.RowCount,
		Explanation:  explainResult,
		Confidence:   genResult.Confidence,
		TotalTokens:  totalTokens,
		TotalCostUSD: totalCost,
		DurationMS:   duration.Milliseconds(),
		TraceID:      traceID,
	}

	if p.Metrics != nil {
		p.Metrics.QuestionDuration.Record(ctx, duration.Seconds(), questionTypeAttr)
	}

	// Save to history
	_, _ = db.InsertQueryHistory(ctx, p.DB, db.InsertHistoryParams{
		Question:     question,
		QuestionType: parsed.QuestionType,
		GeneratedSQL: validated.SafeSQL,
		Confidence:   genResult.Confidence,
		RowCount:     execResult.RowCount,
		ExecutionMS:  int(execResult.Duration.Milliseconds()),
		TotalTokens:  result.TotalTokens,
		TotalCostUSD: result.TotalCostUSD,
		Explanation:  explainResult.Summary,
		TraceID:      traceID,
	})

	span.SetAttributes(
		attribute.String("nlsql.question_type", parsed.QuestionType),
		attribute.Float64("nlsql.confidence", genResult.Confidence),
		attribute.Int("nlsql.row_count", execResult.RowCount),
		attribute.Int64("nlsql.duration_ms", duration.Milliseconds()),
	)

	return result, nil
}
