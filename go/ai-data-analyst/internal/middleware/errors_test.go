package middleware

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"go.opentelemetry.io/otel/codes"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
	"go.opentelemetry.io/otel/sdk/trace/tracetest"
)

// serve runs the handler under a recorded span, the way the HTTP middleware
// runs it under the otelhttp server span.
func serve(t *testing.T, h http.Handler, req *http.Request) (*httptest.ResponseRecorder, tracetest.SpanStub) {
	t.Helper()

	exporter := tracetest.NewInMemoryExporter()
	tp := sdktrace.NewTracerProvider(sdktrace.WithSyncer(exporter))
	t.Cleanup(func() { _ = tp.Shutdown(context.Background()) })

	ctx, span := tp.Tracer("test").Start(req.Context(), "POST /api/ask")
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req.WithContext(ctx))
	span.End()

	spans := exporter.GetSpans()
	require.Len(t, spans, 1)
	return rec, spans[0]
}

func TestErrorStatusMarksClientErrors(t *testing.T) {
	handler := ErrorStatus(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusBadRequest)
	}))

	_, span := serve(t, handler, httptest.NewRequest(http.MethodPost, "/api/ask", nil))

	assert.Equal(t, codes.Error, span.Status.Code)
	found := false
	for _, kv := range span.Attributes {
		if string(kv.Key) == "error.type" {
			found = true
			assert.Equal(t, "400", kv.Value.AsString())
		}
	}
	assert.True(t, found, "a 4xx response sets error.type on the server span")
}

func TestErrorStatusLeavesSuccessAlone(t *testing.T) {
	handler := ErrorStatus(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))

	_, span := serve(t, handler, httptest.NewRequest(http.MethodGet, "/api/schema", nil))

	assert.NotEqual(t, codes.Error, span.Status.Code)
}

func TestRecoveryRecordsPanicOnActiveSpan(t *testing.T) {
	handler := Recovery(http.HandlerFunc(func(http.ResponseWriter, *http.Request) {
		panic("boom")
	}))

	rec, span := serve(t, handler, httptest.NewRequest(http.MethodPost, "/api/ask", nil))

	assert.Equal(t, http.StatusInternalServerError, rec.Code)
	assert.Equal(t, codes.Error, span.Status.Code)
	require.Len(t, span.Events, 1)
	assert.Equal(t, "exception", span.Events[0].Name)
}
