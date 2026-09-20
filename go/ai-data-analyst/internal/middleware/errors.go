package middleware

import (
	"fmt"
	"net/http"
	"strconv"

	"ai-data-analyst/internal/telemetry"

	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/codes"
	"go.opentelemetry.io/otel/trace"
)

type statusWriter struct {
	http.ResponseWriter
	status int
}

func (w *statusWriter) WriteHeader(status int) {
	w.status = status
	w.ResponseWriter.WriteHeader(status)
}

// ErrorStatus marks the HTTP server span as failed for every response from 400
// up. Those responses carry no exception, so only error.type and the status are
// recorded.
func ErrorStatus(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		sw := &statusWriter{ResponseWriter: w, status: http.StatusOK}
		next.ServeHTTP(sw, r)

		if sw.status < 400 {
			return
		}
		span := trace.SpanFromContext(r.Context())
		span.SetAttributes(attribute.String("error.type", strconv.Itoa(sw.status)))
		span.SetStatus(codes.Error, http.StatusText(sw.status))
	})
}

// Recovery records a panic on the active span before returning a 500, so a
// failure that never reached a handler still shows up in the trace.
func Recovery(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		defer func() {
			rec := recover()
			if rec == nil {
				return
			}
			err, ok := rec.(error)
			if !ok {
				err = fmt.Errorf("%v", rec)
			}
			telemetry.RecordErrorOnActiveSpan(r.Context(), err, fmt.Sprintf("%T", rec))

			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusInternalServerError)
			_, _ = w.Write([]byte(`{"error":"internal server error"}`))
		}()

		next.ServeHTTP(w, r)
	})
}
