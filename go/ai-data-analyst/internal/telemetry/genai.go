package telemetry

import (
	"context"

	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/metric"
)

type GenAIMetrics struct {
	TokenUsage        metric.Float64Histogram
	OperationDuration metric.Float64Histogram
	Cost              metric.Float64Counter
	RetryCount        metric.Int64Counter
	FallbackCount     metric.Int64Counter
	ErrorCount        metric.Int64Counter

	QuestionDuration   metric.Float64Histogram
	SQLValid           metric.Int64Counter
	QueryRows          metric.Float64Histogram
	QueryExecutionTime metric.Float64Histogram
	Confidence         metric.Float64Histogram
}

func NewGenAIMetrics(m metric.Meter) (*GenAIMetrics, error) {
	tokenUsage, err := m.Float64Histogram("gen_ai.client.token.usage",
		metric.WithUnit("{token}"),
		metric.WithDescription("Number of tokens used per LLM call"),
	)
	if err != nil {
		return nil, err
	}

	operationDuration, err := m.Float64Histogram("gen_ai.client.operation.duration",
		metric.WithUnit("s"),
		metric.WithDescription("Wall-clock duration of LLM API call"),
	)
	if err != nil {
		return nil, err
	}

	cost, err := m.Float64Counter("base14.gen_ai.cost",
		metric.WithUnit("usd"),
		metric.WithDescription("Cumulative cost of LLM calls in USD"),
	)
	if err != nil {
		return nil, err
	}

	retryCount, err := m.Int64Counter("base14.gen_ai.retry.count",
		metric.WithUnit("{retry}"),
		metric.WithDescription("Number of retry attempts, excluding the initial attempt"),
	)
	if err != nil {
		return nil, err
	}

	fallbackCount, err := m.Int64Counter("base14.gen_ai.fallback.count",
		metric.WithUnit("{fallback}"),
		metric.WithDescription("Number of fallback provider triggers"),
	)
	if err != nil {
		return nil, err
	}

	errorCount, err := m.Int64Counter("base14.gen_ai.error.count",
		metric.WithUnit("{error}"),
		metric.WithDescription("Number of LLM call errors by provider and type"),
	)
	if err != nil {
		return nil, err
	}

	questionDuration, err := m.Float64Histogram("base14.nlsql.question.duration",
		metric.WithUnit("s"),
		metric.WithDescription("Total question-to-answer duration"),
	)
	if err != nil {
		return nil, err
	}

	sqlValid, err := m.Int64Counter("base14.nlsql.sql.valid",
		metric.WithUnit("1"),
		metric.WithDescription("SQL validation outcomes"),
	)
	if err != nil {
		return nil, err
	}

	queryRows, err := m.Float64Histogram("base14.nlsql.query.rows",
		metric.WithUnit("{row}"),
		metric.WithDescription("Number of rows returned per query"),
	)
	if err != nil {
		return nil, err
	}

	queryExecutionTime, err := m.Float64Histogram("base14.nlsql.query.execution_time",
		metric.WithUnit("ms"),
		metric.WithDescription("SQL query execution time in milliseconds"),
	)
	if err != nil {
		return nil, err
	}

	confidence, err := m.Float64Histogram("base14.nlsql.confidence",
		metric.WithUnit("1"),
		metric.WithDescription("LLM confidence score for SQL generation"),
	)
	if err != nil {
		return nil, err
	}

	return &GenAIMetrics{
		TokenUsage:         tokenUsage,
		OperationDuration:  operationDuration,
		Cost:               cost,
		RetryCount:         retryCount,
		FallbackCount:      fallbackCount,
		ErrorCount:         errorCount,
		QuestionDuration:   questionDuration,
		SQLValid:           sqlValid,
		QueryRows:          queryRows,
		QueryExecutionTime: queryExecutionTime,
		Confidence:         confidence,
	}, nil
}

// CallAttrs identifies one LLM call on every metric it produces.
type CallAttrs struct {
	Provider string
	Model    string
	Stage    string
}

func (a CallAttrs) keyValues() []attribute.KeyValue {
	kv := []attribute.KeyValue{
		attribute.String("gen_ai.operation.name", "chat"),
		attribute.String("gen_ai.provider.name", a.Provider),
		attribute.String("gen_ai.request.model", a.Model),
	}
	if a.Stage != "" {
		kv = append(kv, attribute.String("base14.nlsql.stage", a.Stage))
	}
	return kv
}

func (g *GenAIMetrics) RecordUsage(ctx context.Context, a CallAttrs, inputTokens, outputTokens int, costUSD float64) {
	base := a.keyValues()

	g.TokenUsage.Record(ctx, float64(inputTokens),
		metric.WithAttributes(base...),
		metric.WithAttributes(attribute.String("gen_ai.token.type", "input")),
	)
	g.TokenUsage.Record(ctx, float64(outputTokens),
		metric.WithAttributes(base...),
		metric.WithAttributes(attribute.String("gen_ai.token.type", "output")),
	)
	g.Cost.Add(ctx, costUSD, metric.WithAttributes(base...))
}

// RecordDuration records the call duration on success and on failure. Pass an
// empty errorType for a successful call.
func (g *GenAIMetrics) RecordDuration(ctx context.Context, a CallAttrs, seconds float64, errorType string) {
	attrs := a.keyValues()
	if errorType != "" {
		attrs = append(attrs, attribute.String("error.type", errorType))
	}
	g.OperationDuration.Record(ctx, seconds, metric.WithAttributes(attrs...))
}

func (g *GenAIMetrics) RecordError(ctx context.Context, a CallAttrs, errorType string) {
	g.ErrorCount.Add(ctx, 1, metric.WithAttributes(
		attribute.String("gen_ai.provider.name", a.Provider),
		attribute.String("gen_ai.request.model", a.Model),
		attribute.String("error.type", errorType),
	))
}

func (g *GenAIMetrics) RecordRetry(ctx context.Context, a CallAttrs, errorType string, attempt int) {
	g.RetryCount.Add(ctx, 1, metric.WithAttributes(
		attribute.String("gen_ai.provider.name", a.Provider),
		attribute.String("error.type", errorType),
		attribute.Int("base14.retry.attempt", attempt),
	))
}

func (g *GenAIMetrics) RecordFallback(ctx context.Context, from, to, errorType string) {
	g.FallbackCount.Add(ctx, 1, metric.WithAttributes(
		attribute.String("gen_ai.provider.name", from),
		attribute.String("base14.gen_ai.fallback.provider", to),
		attribute.String("error.type", errorType),
	))
}

func WithSQLValid(valid bool) metric.MeasurementOption {
	return metric.WithAttributes(attribute.Bool("base14.nlsql.valid", valid))
}

func WithQuestionType(questionType string) metric.MeasurementOption {
	return metric.WithAttributes(attribute.String("base14.nlsql.question_type", questionType))
}
