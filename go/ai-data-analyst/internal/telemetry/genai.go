package telemetry

import (
	"context"

	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/metric"
)

type GenAIMetrics struct {
	InputTokens       metric.Int64Histogram
	OutputTokens      metric.Int64Histogram
	InferenceDuration metric.Float64Histogram
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

var (
	tokenBuckets    = []float64{1, 4, 16, 64, 256, 1024, 4096, 16384, 65536, 262144, 1048576, 4194304, 16777216, 67108864}
	durationBuckets = []float64{0.01, 0.02, 0.04, 0.08, 0.16, 0.32, 0.64, 1.28, 2.56, 5.12, 10.24, 20.48, 40.96, 81.92}
)

func NewGenAIMetrics(m metric.Meter) (*GenAIMetrics, error) {
	inputTokens, err := m.Int64Histogram("gen_ai.client.inference.operation.input_tokens",
		metric.WithUnit("{token}"),
		metric.WithDescription("Input tokens per inference call"),
		metric.WithExplicitBucketBoundaries(tokenBuckets...),
	)
	if err != nil {
		return nil, err
	}

	outputTokens, err := m.Int64Histogram("gen_ai.client.inference.operation.output_tokens",
		metric.WithUnit("{token}"),
		metric.WithDescription("Output tokens per inference call"),
		metric.WithExplicitBucketBoundaries(tokenBuckets...),
	)
	if err != nil {
		return nil, err
	}

	inferenceDuration, err := m.Float64Histogram("gen_ai.client.inference.duration",
		metric.WithUnit("s"),
		metric.WithDescription("Wall-clock duration of an inference call"),
		metric.WithExplicitBucketBoundaries(durationBuckets...),
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
		InputTokens:        inputTokens,
		OutputTokens:       outputTokens,
		InferenceDuration:  inferenceDuration,
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

// RecordInference records the duration and token histograms for one
// inference call, on success and on failure. Pass an empty errorType for a
// successful call, and zero tokens when the provider returned no usage.
func (g *GenAIMetrics) RecordInference(ctx context.Context, a CallAttrs, seconds float64, inputTokens, outputTokens int, errorType string) {
	attrs := a.keyValues()
	if errorType != "" {
		attrs = append(attrs, attribute.String("error.type", errorType))
	}
	opt := metric.WithAttributes(attrs...)

	g.InferenceDuration.Record(ctx, seconds, opt)
	g.InputTokens.Record(ctx, int64(inputTokens), opt)
	g.OutputTokens.Record(ctx, int64(outputTokens), opt)
}

func (g *GenAIMetrics) RecordCost(ctx context.Context, a CallAttrs, costUSD float64) {
	g.Cost.Add(ctx, costUSD, metric.WithAttributes(a.keyValues()...))
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
