package telemetry

import (
	"context"

	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/codes"
	"go.opentelemetry.io/otel/trace"
)

// RecordError applies the three-step error pattern to a span: the exception,
// the error.type classification and the ERROR status.
func RecordError(span trace.Span, err error, errorType string) {
	span.RecordError(err)
	span.SetAttributes(attribute.String("error.type", errorType))
	span.SetStatus(codes.Error, err.Error())
}

// RecordErrorOnActiveSpan applies the same pattern to whichever span is active,
// for error paths that do not own a span of their own.
func RecordErrorOnActiveSpan(ctx context.Context, err error, errorType string) {
	RecordError(trace.SpanFromContext(ctx), err, errorType)
}
