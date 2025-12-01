package database

import (
	"fmt"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/codes"
	"go.opentelemetry.io/otel/trace"
	"gorm.io/gorm"
)

const (
	callBackBeforeName = "otel:before"
	callBackAfterName  = "otel:after"
)

var tracer = otel.Tracer("gorm")

type gormTracer struct{}

// RegisterCallbacks registers GORM callbacks for tracing
func RegisterCallbacks(db *gorm.DB) error {
	callbacks := &gormTracer{}

	// Register callbacks for all CRUD operations
	if err := db.Callback().Create().Before("gorm:create").Register(callBackBeforeName, callbacks.before("gorm:create")); err != nil {
		return err
	}
	if err := db.Callback().Create().After("gorm:create").Register(callBackAfterName, callbacks.after()); err != nil {
		return err
	}

	if err := db.Callback().Query().Before("gorm:query").Register(callBackBeforeName, callbacks.before("gorm:query")); err != nil {
		return err
	}
	if err := db.Callback().Query().After("gorm:query").Register(callBackAfterName, callbacks.after()); err != nil {
		return err
	}

	if err := db.Callback().Update().Before("gorm:update").Register(callBackBeforeName, callbacks.before("gorm:update")); err != nil {
		return err
	}
	if err := db.Callback().Update().After("gorm:update").Register(callBackAfterName, callbacks.after()); err != nil {
		return err
	}

	if err := db.Callback().Delete().Before("gorm:delete").Register(callBackBeforeName, callbacks.before("gorm:delete")); err != nil {
		return err
	}
	if err := db.Callback().Delete().After("gorm:delete").Register(callBackAfterName, callbacks.after()); err != nil {
		return err
	}

	if err := db.Callback().Row().Before("gorm:row").Register(callBackBeforeName, callbacks.before("gorm:row")); err != nil {
		return err
	}
	if err := db.Callback().Row().After("gorm:row").Register(callBackAfterName, callbacks.after()); err != nil {
		return err
	}

	if err := db.Callback().Raw().Before("gorm:raw").Register(callBackBeforeName, callbacks.before("gorm:raw")); err != nil {
		return err
	}
	if err := db.Callback().Raw().After("gorm:raw").Register(callBackAfterName, callbacks.after()); err != nil {
		return err
	}

	return nil
}

func (g *gormTracer) before(operation string) func(*gorm.DB) {
	return func(db *gorm.DB) {
		ctx := db.Statement.Context
		if ctx == nil {
			return
		}

		// Start a new span
		ctx, span := tracer.Start(ctx, operation,
			trace.WithSpanKind(trace.SpanKindClient),
			trace.WithAttributes(
				attribute.String("db.system", "postgresql"),
				attribute.String("db.name", db.Statement.Table),
			),
		)

		// Store span in context
		db.Statement.Context = ctx
		db.InstanceSet("otel:span", span)
	}
}

func (g *gormTracer) after() func(*gorm.DB) {
	return func(db *gorm.DB) {
		// Retrieve span from context
		spanInterface, ok := db.InstanceGet("otel:span")
		if !ok {
			return
		}

		span, ok := spanInterface.(trace.Span)
		if !ok {
			return
		}
		defer span.End()

		// Add SQL query and parameters
		if db.Statement.SQL.String() != "" {
			span.SetAttributes(
				attribute.String("db.statement", db.Statement.SQL.String()),
			)
		}

		// Add row count
		span.SetAttributes(
			attribute.Int64("db.rows_affected", db.Statement.RowsAffected),
		)

		// Record error if any
		if db.Error != nil && db.Error != gorm.ErrRecordNotFound {
			span.RecordError(db.Error)
			span.SetStatus(codes.Error, db.Error.Error())
		} else {
			span.SetStatus(codes.Ok, "")
		}

		// Add table name if available
		if db.Statement.Table != "" {
			span.SetAttributes(
				attribute.String("db.sql.table", db.Statement.Table),
			)
		}
	}
}

func (g *gormTracer) String() string {
	return fmt.Sprintf("gorm-otel-tracer")
}
