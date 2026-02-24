package pipeline

import (
	"context"
	"fmt"
	"time"

	"ai-data-analyst/internal/db"

	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/codes"
	"go.opentelemetry.io/otel/trace"
)

type ExecuteResult struct {
	Columns  []string `json:"columns"`
	Rows     [][]any  `json:"rows"`
	RowCount int      `json:"row_count"`
	Duration time.Duration
}

func Execute(ctx context.Context, tracer trace.Tracer, q db.Querier, sql string) (*ExecuteResult, error) {
	ctx, span := tracer.Start(ctx, "pipeline_stage execute")
	defer span.End()

	span.SetAttributes(
		attribute.String("nlsql.stage", "execute"),
		attribute.String("db.system", "postgresql"),
		attribute.String("db.statement", sql),
		attribute.String("db.operation", "SELECT"),
	)

	start := time.Now()

	// Set read-only transaction and statement timeout
	_, err := q.Exec(ctx, "SET TRANSACTION READ ONLY")
	if err != nil {
		span.SetStatus(codes.Error, err.Error())
		return nil, fmt.Errorf("failed to set read-only transaction: %w", err)
	}

	_, err = q.Exec(ctx, "SET LOCAL statement_timeout = '10s'")
	if err != nil {
		span.SetStatus(codes.Error, err.Error())
		return nil, fmt.Errorf("failed to set statement timeout: %w", err)
	}

	rows, err := q.Query(ctx, sql)
	if err != nil {
		span.SetStatus(codes.Error, err.Error())
		span.SetAttributes(attribute.String("error.type", fmt.Sprintf("%T", err)))
		return nil, fmt.Errorf("query execution failed: %w", err)
	}
	defer rows.Close()

	// Extract column names
	fields := rows.FieldDescriptions()
	columns := make([]string, len(fields))
	for i, f := range fields {
		columns[i] = string(f.Name)
	}

	// Scan rows dynamically
	var resultRows [][]any
	for rows.Next() {
		values, err := rows.Values()
		if err != nil {
			span.SetStatus(codes.Error, err.Error())
			return nil, fmt.Errorf("row scan failed: %w", err)
		}

		// Convert pgx types to JSON-friendly values
		row := make([]any, len(values))
		for i, v := range values {
			row[i] = convertPgValue(v)
		}
		resultRows = append(resultRows, row)
	}

	if err := rows.Err(); err != nil {
		span.SetStatus(codes.Error, err.Error())
		return nil, fmt.Errorf("rows iteration error: %w", err)
	}

	duration := time.Since(start)
	result := &ExecuteResult{
		Columns:  columns,
		Rows:     resultRows,
		RowCount: len(resultRows),
		Duration: duration,
	}

	span.SetAttributes(
		attribute.Int("nlsql.row_count", result.RowCount),
		attribute.Int("nlsql.column_count", len(columns)),
		attribute.Int("nlsql.execution_ms", int(duration.Milliseconds())),
	)

	return result, nil
}

func convertPgValue(v any) any {
	if v == nil {
		return nil
	}
	switch val := v.(type) {
	case fmt.Stringer:
		return val.String()
	default:
		return v
	}
}
