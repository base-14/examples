package logging

import (
	"context"
	"os"
	"time"

	"github.com/rs/zerolog"
	"go.opentelemetry.io/otel/trace"
)

var logger zerolog.Logger

func Init(isDevelopment bool) {
	zerolog.TimeFieldFormat = time.RFC3339

	if isDevelopment {
		logger = zerolog.New(zerolog.ConsoleWriter{Out: os.Stdout, TimeFormat: time.RFC3339}).
			With().
			Timestamp().
			Caller().
			Logger()
	} else {
		logger = zerolog.New(os.Stdout).
			With().
			Timestamp().
			Logger()
	}
}

func Logger() *zerolog.Logger {
	return &logger
}

func WithContext(ctx context.Context) zerolog.Logger {
	span := trace.SpanFromContext(ctx)
	if !span.SpanContext().IsValid() {
		return logger
	}

	return logger.With().
		Str("traceId", span.SpanContext().TraceID().String()).
		Str("spanId", span.SpanContext().SpanID().String()).
		Logger()
}

func Info(ctx context.Context) *zerolog.Event {
	l := WithContext(ctx)
	return l.Info()
}

func Error(ctx context.Context) *zerolog.Event {
	l := WithContext(ctx)
	return l.Error()
}

func Debug(ctx context.Context) *zerolog.Event {
	l := WithContext(ctx)
	return l.Debug()
}

func Warn(ctx context.Context) *zerolog.Event {
	l := WithContext(ctx)
	return l.Warn()
}
