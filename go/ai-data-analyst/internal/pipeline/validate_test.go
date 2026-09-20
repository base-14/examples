package pipeline

import (
	"context"
	"strings"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
	"go.opentelemetry.io/otel/sdk/trace/tracetest"
	"go.opentelemetry.io/otel/trace"
)

func validate(sql string) *ValidateResult {
	tp := testTracer()
	return Validate(context.Background(), tp.Tracer("test"), sql)
}

func TestValidateAcceptsReadOnlyQueries(t *testing.T) {
	tests := []struct {
		name string
		sql  string
	}{
		{"simple select", "SELECT name FROM countries LIMIT 10"},
		{"join", "SELECT c.name, iv.value FROM countries c JOIN indicator_values iv ON c.id = iv.country_id LIMIT 10"},
		{"subquery", "SELECT name FROM countries WHERE id IN (SELECT country_id FROM indicator_values WHERE year = 2023) LIMIT 10"},
		{"cte", "WITH top_countries AS (SELECT country_id FROM indicator_values WHERE year = 2023) SELECT name FROM countries LIMIT 10"},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			r := validate(tt.sql)
			assert.True(t, r.Valid)
			assert.Empty(t, r.Violations())
		})
	}
}

func TestValidateRejectsUnsafeStatements(t *testing.T) {
	tests := []struct {
		name  string
		sql   string
		check string
	}{
		{"insert", "INSERT INTO countries VALUES (1, 'Test', 'TST', 'Test', 'Test')", "no_mutation"},
		{"drop", "DROP TABLE countries", "no_mutation"},
		{"delete", "DELETE FROM countries WHERE id = 1", "no_mutation"},
		{"update", "UPDATE countries SET name = 'Test' WHERE id = 1", "no_mutation"},
		{"execute", "EXECUTE my_plan", "no_mutation"},
		{"system schema", "SELECT * FROM pg_catalog.pg_tables", "no_system_schema"},
		{"multiple statements", "SELECT 1; SELECT 2", "single_statement"},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			r := validate(tt.sql)
			assert.False(t, r.Valid)
			assert.Contains(t, strings.Join(r.Violations(), " | "), tt.check)
		})
	}
}

func TestValidateInjectLimit(t *testing.T) {
	r := validate("SELECT name FROM countries")
	assert.True(t, r.Valid)
	assert.Contains(t, r.SafeSQL, "LIMIT 50")
}

func TestValidateKeepExistingLimit(t *testing.T) {
	r := validate("SELECT name FROM countries LIMIT 10")
	assert.True(t, r.Valid)
	assert.Contains(t, r.SafeSQL, "LIMIT 10")
	assert.NotContains(t, r.SafeSQL, "LIMIT 50")
}

func TestValidateEmitsOneEvaluationEventPerCheck(t *testing.T) {
	exporter := tracetest.NewInMemoryExporter()
	tp := sdktrace.NewTracerProvider(sdktrace.WithSyncer(exporter))
	t.Cleanup(func() { _ = tp.Shutdown(context.Background()) })

	Validate(context.Background(), tp.Tracer("test"), "DELETE FROM countries")

	spans := exporter.GetSpans()
	require.Len(t, spans, 1)
	span := spans[0]
	assert.Equal(t, "output_guardrails", span.Name)
	assert.Equal(t, trace.SpanKindInternal, span.SpanKind)
	require.Len(t, span.Events, 4, "one event per guardrail check")

	byName := map[string]map[string]any{}
	for _, e := range span.Events {
		assert.Equal(t, "gen_ai.evaluation.result", e.Name)
		attrs := map[string]any{}
		for _, kv := range e.Attributes {
			attrs[string(kv.Key)] = kv.Value.AsInterface()
		}
		byName[attrs["gen_ai.evaluation.name"].(string)] = attrs
	}

	failed := byName["no_mutation"]
	require.NotNil(t, failed)
	assert.Equal(t, 0.0, failed["gen_ai.evaluation.score.value"])
	assert.Equal(t, "fail", failed["gen_ai.evaluation.score.label"])
	assert.Contains(t, failed["gen_ai.evaluation.explanation"], "DELETE")

	passed := byName["no_system_schema"]
	require.NotNil(t, passed)
	assert.Equal(t, 1.0, passed["gen_ai.evaluation.score.value"])
	assert.Equal(t, "pass", passed["gen_ai.evaluation.score.label"])
	assert.NotContains(t, passed, "gen_ai.evaluation.explanation")
}
