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

	// Create OTel handler using the global logger provider (set by telemetry.Init)
	otelHandler := otelslog.NewHandler(serviceName, otelslog.WithLoggerProvider(global.GetLoggerProvider()))

	// Create JSON handler for stdout
	jsonHandler := slog.NewJSONHandler(os.Stdout, opts)

	// Use a multi-handler that writes to both
	multiHandler := &multiHandler{
		handlers: []slog.Handler{otelHandler, jsonHandler},
	}

	logger = slog.New(multiHandler).With(
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

func WithContext(ctx context.Context) *slog.Logger {
	l := Logger()
	span := trace.SpanFromContext(ctx)
	if !span.SpanContext().IsValid() {
		return l
	}
	return l.With(
		slog.String("traceId", span.SpanContext().TraceID().String()),
		slog.String("spanId", span.SpanContext().SpanID().String()),
	)
}

func Debug(ctx context.Context, msg string, args ...any) {
	WithContext(ctx).DebugContext(ctx, msg, args...)
}

func Info(ctx context.Context, msg string, args ...any) {
	WithContext(ctx).InfoContext(ctx, msg, args...)
}

func Warn(ctx context.Context, msg string, args ...any) {
	WithContext(ctx).WarnContext(ctx, msg, args...)
}

func Error(ctx context.Context, msg string, args ...any) {
	WithContext(ctx).ErrorContext(ctx, msg, args...)
}

// multiHandler sends logs to multiple handlers
type multiHandler struct {
	handlers []slog.Handler
}

func (h *multiHandler) Enabled(ctx context.Context, level slog.Level) bool {
	for _, handler := range h.handlers {
		if handler.Enabled(ctx, level) {
			return true
		}
	}
	return false
}

func (h *multiHandler) Handle(ctx context.Context, record slog.Record) error {
	for _, handler := range h.handlers {
		if handler.Enabled(ctx, record.Level) {
			if err := handler.Handle(ctx, record); err != nil {
				return err
			}
		}
	}
	return nil
}

func (h *multiHandler) WithAttrs(attrs []slog.Attr) slog.Handler {
	handlers := make([]slog.Handler, len(h.handlers))
	for i, handler := range h.handlers {
		handlers[i] = handler.WithAttrs(attrs)
	}
	return &multiHandler{handlers: handlers}
}

func (h *multiHandler) WithGroup(name string) slog.Handler {
	handlers := make([]slog.Handler, len(h.handlers))
	for i, handler := range h.handlers {
		handlers[i] = handler.WithGroup(name)
	}
	return &multiHandler{handlers: handlers}
}
