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

	cost, err := m.Float64Counter("gen_ai.client.cost",
		metric.WithUnit("usd"),
		metric.WithDescription("Cumulative cost of LLM calls in USD"),
	)
	if err != nil {
		return nil, err
	}

	retryCount, err := m.Int64Counter("gen_ai.client.retry.count",
		metric.WithUnit("{retry}"),
		metric.WithDescription("Number of retry attempts"),
	)
	if err != nil {
		return nil, err
	}

	fallbackCount, err := m.Int64Counter("gen_ai.client.fallback.count",
		metric.WithUnit("{fallback}"),
		metric.WithDescription("Number of fallback provider triggers"),
	)
	if err != nil {
		return nil, err
	}

	errorCount, err := m.Int64Counter("gen_ai.client.error.count",
		metric.WithUnit("{error}"),
		metric.WithDescription("Number of LLM call errors"),
	)
	if err != nil {
		return nil, err
	}

	questionDuration, err := m.Float64Histogram("nlsql.question.duration",
		metric.WithUnit("s"),
		metric.WithDescription("Total question-to-answer duration"),
	)
	if err != nil {
		return nil, err
	}

	sqlValid, err := m.Int64Counter("nlsql.sql.valid",
		metric.WithUnit("1"),
		metric.WithDescription("SQL validation outcomes"),
	)
	if err != nil {
		return nil, err
	}

	queryRows, err := m.Float64Histogram("nlsql.query.rows",
		metric.WithUnit("{row}"),
		metric.WithDescription("Number of rows returned per query"),
	)
	if err != nil {
		return nil, err
	}

	queryExecutionTime, err := m.Float64Histogram("nlsql.query.execution_time",
		metric.WithUnit("ms"),
		metric.WithDescription("SQL query execution time in milliseconds"),
	)
	if err != nil {
		return nil, err
	}

	confidence, err := m.Float64Histogram("nlsql.confidence",
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

type RecordParams struct {
	Provider     string
	Model        string
	Stage        string
	InputTokens  int
	OutputTokens int
	DurationSec  float64
	CostUSD      float64
}

func (g *GenAIMetrics) RecordGenAIMetrics(ctx context.Context, p RecordParams) {
	baseAttrs := []attribute.KeyValue{
		attribute.String("gen_ai.operation.name", "chat"),
		attribute.String("gen_ai.provider.name", p.Provider),
		attribute.String("gen_ai.request.model", p.Model),
	}
	if p.Stage != "" {
		baseAttrs = append(baseAttrs, attribute.String("nlsql.stage", p.Stage))
	}
	attrs := metric.WithAttributes(baseAttrs...)

	g.TokenUsage.Record(ctx, float64(p.InputTokens),
		attrs,
		metric.WithAttributes(attribute.String("gen_ai.token.type", "input")),
	)
	g.TokenUsage.Record(ctx, float64(p.OutputTokens),
		attrs,
		metric.WithAttributes(attribute.String("gen_ai.token.type", "output")),
	)
	g.OperationDuration.Record(ctx, p.DurationSec, attrs)
	g.Cost.Add(ctx, p.CostUSD, attrs)
}

func WithProviderModel(provider, model string) metric.MeasurementOption {
	return metric.WithAttributes(
		attribute.String("gen_ai.provider.name", provider),
		attribute.String("gen_ai.request.model", model),
	)
}

func WithBoolAttr(key string, val bool) metric.MeasurementOption {
	return metric.WithAttributes(attribute.Bool(key, val))
}

func WithQuestionType(qt string) metric.MeasurementOption {
	return metric.WithAttributes(attribute.String("nlsql.question_type", qt))
}
