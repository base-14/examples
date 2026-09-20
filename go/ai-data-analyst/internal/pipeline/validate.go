package pipeline

import (
	"context"
	"regexp"
	"strings"

	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/trace"
)

// Check is the outcome of one guardrail applied to the generated SQL.
type Check struct {
	Name        string `json:"name"`
	Passed      bool   `json:"passed"`
	Explanation string `json:"explanation,omitempty"`
}

type ValidateResult struct {
	Valid   bool    `json:"valid"`
	SafeSQL string  `json:"safe_sql"`
	Checks  []Check `json:"checks"`
}

// Violations lists the failed checks as "name: explanation" strings.
func (r *ValidateResult) Violations() []string {
	var out []string
	for _, c := range r.Checks {
		if !c.Passed {
			out = append(out, c.Name+": "+c.Explanation)
		}
	}
	return out
}

var mutationKeywords = []string{
	"INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE",
	"TRUNCATE", "EXECUTE", "PREPARE", "GRANT", "REVOKE",
}

var systemSchemas = []string{
	"pg_catalog", "information_schema", "pg_temp", "pg_toast",
}

var (
	limitPattern    = regexp.MustCompile(`(?i)\bLIMIT\s+\d+`)
	semicolonSplit  = regexp.MustCompile(`;\s*\S`)
	keywordPatterns = keywordMatchers()
)

func keywordMatchers() map[string]*regexp.Regexp {
	m := make(map[string]*regexp.Regexp, len(mutationKeywords))
	for _, kw := range mutationKeywords {
		m[kw] = regexp.MustCompile(`(?i)\b` + kw + `\b`)
	}
	return m
}

// Validate runs the output guardrails over generated SQL and reports each check
// as a gen_ai.evaluation.result event on an output_guardrails span.
func Validate(ctx context.Context, tracer trace.Tracer, sql string) *ValidateResult {
	_, span := tracer.Start(ctx, "output_guardrails", trace.WithSpanKind(trace.SpanKindInternal))
	defer span.End()

	result := &ValidateResult{
		Valid:   true,
		SafeSQL: strings.TrimSpace(sql),
		Checks: []Check{
			checkNoMutation(sql),
			checkNoSystemSchema(sql),
			checkSingleStatement(sql),
			checkSelectOnly(sql),
		},
	}

	for _, c := range result.Checks {
		if !c.Passed {
			result.Valid = false
		}
		recordEvaluation(span, c)
	}

	limitInjected := false
	if result.Valid && !limitPattern.MatchString(sql) {
		result.SafeSQL = strings.TrimRight(result.SafeSQL, ";") + " LIMIT 50"
		limitInjected = true
	}
	result.SafeSQL = strings.TrimRight(result.SafeSQL, ";")

	span.SetAttributes(
		attribute.String("base14.nlsql.stage", "validate"),
		attribute.Bool("base14.nlsql.valid", result.Valid),
		attribute.Int("base14.nlsql.violations_count", len(result.Violations())),
		attribute.Bool("base14.nlsql.limit_injected", limitInjected),
	)

	return result
}

func recordEvaluation(span trace.Span, c Check) {
	score := 0.0
	label := "fail"
	if c.Passed {
		score = 1.0
		label = "pass"
	}

	attrs := []attribute.KeyValue{
		attribute.String("gen_ai.evaluation.name", c.Name),
		attribute.Float64("gen_ai.evaluation.score.value", score),
		attribute.String("gen_ai.evaluation.score.label", label),
	}
	if !c.Passed {
		attrs = append(attrs, attribute.String("gen_ai.evaluation.explanation", c.Explanation))
	}

	span.AddEvent("gen_ai.evaluation.result", trace.WithAttributes(attrs...))
}

func checkNoMutation(sql string) Check {
	for _, kw := range mutationKeywords {
		if keywordPatterns[kw].MatchString(sql) {
			return Check{Name: "no_mutation", Explanation: "statement contains the write keyword " + kw}
		}
	}
	return Check{Name: "no_mutation", Passed: true}
}

func checkNoSystemSchema(sql string) Check {
	lower := strings.ToLower(sql)
	for _, schema := range systemSchemas {
		if strings.Contains(lower, schema) {
			return Check{Name: "no_system_schema", Explanation: "statement reads the system schema " + schema}
		}
	}
	return Check{Name: "no_system_schema", Passed: true}
}

func checkSingleStatement(sql string) Check {
	if semicolonSplit.MatchString(sql) {
		return Check{Name: "single_statement", Explanation: "statement contains more than one SQL statement"}
	}
	return Check{Name: "single_statement", Passed: true}
}

func checkSelectOnly(sql string) Check {
	trimmed := strings.ToUpper(strings.TrimSpace(sql))
	if !strings.HasPrefix(trimmed, "SELECT") && !strings.HasPrefix(trimmed, "WITH") {
		return Check{Name: "select_only", Explanation: "statement does not start with SELECT or WITH"}
	}
	return Check{Name: "select_only", Passed: true}
}
