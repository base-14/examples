package pipeline

import (
	"context"
	"regexp"
	"strings"

	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/trace"
)

type ValidateResult struct {
	Valid      bool     `json:"valid"`
	SafeSQL    string   `json:"safe_sql"`
	Violations []string `json:"violations"`
}

var mutationKeywords = []string{
	"INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE",
	"TRUNCATE", "EXECUTE", "PREPARE", "GRANT", "REVOKE",
}

var systemSchemas = []string{
	"pg_catalog", "information_schema", "pg_temp", "pg_toast",
}

var limitPattern = regexp.MustCompile(`(?i)\bLIMIT\s+\d+`)
var semicolonSplit = regexp.MustCompile(`;\s*\S`)

func Validate(ctx context.Context, tracer trace.Tracer, sql string) *ValidateResult {
	_, span := tracer.Start(ctx, "pipeline_stage validate")
	defer span.End()

	result := &ValidateResult{
		Valid:   true,
		SafeSQL: strings.TrimSpace(sql),
	}

	upper := strings.ToUpper(sql)

	// Check for mutation keywords
	for _, kw := range mutationKeywords {
		pattern := regexp.MustCompile(`(?i)\b` + kw + `\b`)
		if pattern.MatchString(upper) && kw != "CREATE" {
			result.Valid = false
			result.Violations = append(result.Violations, "mutation_detected: "+kw)
		}
		if kw == "CREATE" && !strings.Contains(upper, "CREATE") {
			continue
		}
		if kw == "CREATE" && strings.Contains(upper, "CREATE") {
			result.Valid = false
			result.Violations = append(result.Violations, "ddl_detected: CREATE")
		}
	}

	// Check for system schema access
	lower := strings.ToLower(sql)
	for _, schema := range systemSchemas {
		if strings.Contains(lower, schema) {
			result.Valid = false
			result.Violations = append(result.Violations, "system_schema_access: "+schema)
		}
	}

	// Check for multiple statements (semicolons)
	if semicolonSplit.MatchString(sql) {
		result.Valid = false
		result.Violations = append(result.Violations, "multiple_statements_detected")
	}

	// Must start with SELECT (after trimming whitespace)
	trimmed := strings.TrimSpace(upper)
	if !strings.HasPrefix(trimmed, "SELECT") && !strings.HasPrefix(trimmed, "WITH") {
		result.Valid = false
		result.Violations = append(result.Violations, "not_a_select_statement")
	}

	// Inject LIMIT if missing
	limitInjected := false
	if result.Valid && !limitPattern.MatchString(sql) {
		result.SafeSQL = strings.TrimRight(result.SafeSQL, ";") + " LIMIT 50"
		limitInjected = true
	}

	// Remove trailing semicolons
	result.SafeSQL = strings.TrimRight(result.SafeSQL, ";")

	span.SetAttributes(
		attribute.String("nlsql.stage", "validate"),
		attribute.Bool("nlsql.valid", result.Valid),
		attribute.Int("nlsql.violations_count", len(result.Violations)),
		attribute.Bool("nlsql.limit_injected", limitInjected),
	)

	return result
}
