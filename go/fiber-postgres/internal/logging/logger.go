package logging

import (
	"context"
	"log/slog"
	"os"

	"go.opentelemetry.io/contrib/bridges/otelslog"
	"go.opentelemetry.io/otel/log/global"
	"go.opentelemetry.io/otel/trace"
)

var logger *slog.Logger

func Init(serviceName, environment string) {
	opts := &slog.HandlerOptions{
		Level: slog.LevelInfo,
	}

	if environment == "development" {
		opts.Level = slog.LevelDebug
	}

	stdoutHandler := traceContextHandler{
		Handler: slog.NewJSONHandler(os.Stdout, opts),
	}
	otelHandler := otelslog.NewHandler(serviceName, otelslog.WithLoggerProvider(global.GetLoggerProvider()))

	combined := multiHandler{handlers: []slog.Handler{stdoutHandler, otelHandler}}

	logger = slog.New(combined).With(
		slog.String("service", serviceName),
		slog.String("environment", environment),
	)
	slog.SetDefault(logger)
}

func Logger() *slog.Logger {
	if logger == nil {
		return slog.Default()
	}
	return logger
}

func Debug(ctx context.Context, msg string, args ...any) {
	Logger().DebugContext(ctx, msg, args...)
}

func Info(ctx context.Context, msg string, args ...any) {
	Logger().InfoContext(ctx, msg, args...)
}

func Warn(ctx context.Context, msg string, args ...any) {
	Logger().WarnContext(ctx, msg, args...)
}

func Error(ctx context.Context, msg string, args ...any) {
	Logger().ErrorContext(ctx, msg, args...)
}

// traceContextHandler enriches stdout JSON records with trace_id/span_id from
// context. It wraps the JSON handler only — otelslog already populates these
// fields on the OTLP LogRecord envelope from context, so wrapping that side
// would duplicate them as user attributes.
type traceContextHandler struct {
	slog.Handler
}

func (h traceContextHandler) Handle(ctx context.Context, r slog.Record) error {
	sc := trace.SpanFromContext(ctx).SpanContext()
	if sc.IsValid() {
		r.AddAttrs(
			slog.String("traceId", sc.TraceID().String()),
			slog.String("spanId", sc.SpanID().String()),
		)
	}
	return h.Handler.Handle(ctx, r)
}

func (h traceContextHandler) WithAttrs(attrs []slog.Attr) slog.Handler {
	return traceContextHandler{Handler: h.Handler.WithAttrs(attrs)}
}

func (h traceContextHandler) WithGroup(name string) slog.Handler {
	return traceContextHandler{Handler: h.Handler.WithGroup(name)}
}

// multiHandler fans out a record to multiple slog handlers. Records share
// attribute backing arrays, so each handler receives a Clone() to avoid
// cross-handler mutation.
type multiHandler struct {
	handlers []slog.Handler
}

func (m multiHandler) Enabled(ctx context.Context, level slog.Level) bool {
	for _, h := range m.handlers {
		if h.Enabled(ctx, level) {
			return true
		}
	}
	return false
}

func (m multiHandler) Handle(ctx context.Context, r slog.Record) error {
	var firstErr error
	for _, h := range m.handlers {
		if !h.Enabled(ctx, r.Level) {
			continue
		}
		if err := h.Handle(ctx, r.Clone()); err != nil && firstErr == nil {
			firstErr = err
		}
	}
	return firstErr
}

func (m multiHandler) WithAttrs(attrs []slog.Attr) slog.Handler {
	handlers := make([]slog.Handler, len(m.handlers))
	for i, h := range m.handlers {
		handlers[i] = h.WithAttrs(attrs)
	}
	return multiHandler{handlers: handlers}
}

func (m multiHandler) WithGroup(name string) slog.Handler {
	handlers := make([]slog.Handler, len(m.handlers))
	for i, h := range m.handlers {
		handlers[i] = h.WithGroup(name)
	}
	return multiHandler{handlers: handlers}
}
