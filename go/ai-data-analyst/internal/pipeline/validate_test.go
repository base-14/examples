package pipeline

import (
	"context"
	"testing"

	"github.com/stretchr/testify/assert"
)

func TestValidateSimpleSelect(t *testing.T) {
	tp := testTracer()
	tracer := tp.Tracer("test")
	r := Validate(context.Background(), tracer, "SELECT name FROM countries LIMIT 10")
	assert.True(t, r.Valid)
	assert.Empty(t, r.Violations)
}

func TestValidateJoin(t *testing.T) {
	tp := testTracer()
	tracer := tp.Tracer("test")
	r := Validate(context.Background(), tracer,
		"SELECT c.name, iv.value FROM countries c JOIN indicator_values iv ON c.id = iv.country_id LIMIT 10")
	assert.True(t, r.Valid)
}

func TestValidateSubquery(t *testing.T) {
	tp := testTracer()
	tracer := tp.Tracer("test")
	r := Validate(context.Background(), tracer,
		"SELECT name FROM countries WHERE id IN (SELECT country_id FROM indicator_values WHERE year = 2023) LIMIT 10")
	assert.True(t, r.Valid)
}

func TestValidateWithCTE(t *testing.T) {
	tp := testTracer()
	tracer := tp.Tracer("test")
	r := Validate(context.Background(), tracer,
		"WITH top_countries AS (SELECT country_id FROM indicator_values WHERE year = 2023) SELECT name FROM countries LIMIT 10")
	assert.True(t, r.Valid)
}

func TestValidateRejectInsert(t *testing.T) {
	tp := testTracer()
	tracer := tp.Tracer("test")
	r := Validate(context.Background(), tracer, "INSERT INTO countries VALUES (1, 'Test', 'TST', 'Test', 'Test')")
	assert.False(t, r.Valid)
	assert.Contains(t, r.Violations[0], "mutation_detected")
}

func TestValidateRejectDrop(t *testing.T) {
	tp := testTracer()
	tracer := tp.Tracer("test")
	r := Validate(context.Background(), tracer, "DROP TABLE countries")
	assert.False(t, r.Valid)
}

func TestValidateRejectDelete(t *testing.T) {
	tp := testTracer()
	tracer := tp.Tracer("test")
	r := Validate(context.Background(), tracer, "DELETE FROM countries WHERE id = 1")
	assert.False(t, r.Valid)
}

func TestValidateRejectUpdate(t *testing.T) {
	tp := testTracer()
	tracer := tp.Tracer("test")
	r := Validate(context.Background(), tracer, "UPDATE countries SET name = 'Test' WHERE id = 1")
	assert.False(t, r.Valid)
}

func TestValidateRejectSystemSchema(t *testing.T) {
	tp := testTracer()
	tracer := tp.Tracer("test")
	r := Validate(context.Background(), tracer, "SELECT * FROM pg_catalog.pg_tables")
	assert.False(t, r.Valid)
	assert.Contains(t, r.Violations[0], "system_schema_access")
}

func TestValidateRejectMultipleStatements(t *testing.T) {
	tp := testTracer()
	tracer := tp.Tracer("test")
	r := Validate(context.Background(), tracer, "SELECT 1; DROP TABLE countries")
	assert.False(t, r.Valid)
}

func TestValidateInjectLimit(t *testing.T) {
	tp := testTracer()
	tracer := tp.Tracer("test")
	r := Validate(context.Background(), tracer, "SELECT name FROM countries")
	assert.True(t, r.Valid)
	assert.Contains(t, r.SafeSQL, "LIMIT 50")
}

func TestValidateKeepExistingLimit(t *testing.T) {
	tp := testTracer()
	tracer := tp.Tracer("test")
	r := Validate(context.Background(), tracer, "SELECT name FROM countries LIMIT 10")
	assert.True(t, r.Valid)
	assert.Contains(t, r.SafeSQL, "LIMIT 10")
	assert.NotContains(t, r.SafeSQL, "LIMIT 50")
}

func TestValidateRejectExecute(t *testing.T) {
	tp := testTracer()
	tracer := tp.Tracer("test")
	r := Validate(context.Background(), tracer, "EXECUTE my_plan")
	assert.False(t, r.Valid)
}
