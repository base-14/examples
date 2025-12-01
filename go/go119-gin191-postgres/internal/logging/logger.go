package logging

import (
	"context"
	"io"
	"os"
	"path/filepath"

	"github.com/sirupsen/logrus"
	"go.opentelemetry.io/otel/trace"
)

var log *logrus.Logger

func init() {
	log = logrus.New()

	// Write to both stdout and file
	logDir := os.Getenv("LOG_DIR")
	if logDir == "" {
		logDir = "/var/log/app"
	}

	// Create log directory if it doesn't exist
	if err := os.MkdirAll(logDir, 0755); err == nil {
		logFile := filepath.Join(logDir, "app.log")
		if file, err := os.OpenFile(logFile, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0666); err == nil {
			// Write to both stdout and file
			log.SetOutput(io.MultiWriter(os.Stdout, file))
		} else {
			// Fallback to stdout only
			log.SetOutput(os.Stdout)
		}
	} else {
		// Fallback to stdout only
		log.SetOutput(os.Stdout)
	}

	log.SetFormatter(&logrus.JSONFormatter{
		FieldMap: logrus.FieldMap{
			logrus.FieldKeyTime:  "timestamp",
			logrus.FieldKeyLevel: "severity",
			logrus.FieldKeyMsg:   "message",
		},
	})
	log.SetLevel(logrus.InfoLevel)
}

// WithContext returns a logger with trace context fields (trace_id, span_id) if available
func WithContext(ctx context.Context) *logrus.Entry {
	spanCtx := trace.SpanContextFromContext(ctx)

	fields := logrus.Fields{
		"service.name": os.Getenv("OTEL_SERVICE_NAME"),
	}

	if spanCtx.IsValid() {
		fields["trace_id"] = spanCtx.TraceID().String()
		fields["span_id"] = spanCtx.SpanID().String()
		fields["trace_flags"] = spanCtx.TraceFlags().String()
	}

	return log.WithFields(fields)
}

// Info logs an info message with trace correlation
func Info(ctx context.Context, msg string) {
	WithContext(ctx).Info(msg)
}

// Infof logs a formatted info message with trace correlation
func Infof(ctx context.Context, format string, args ...interface{}) {
	WithContext(ctx).Infof(format, args...)
}

// Error logs an error message with trace correlation
func Error(ctx context.Context, msg string) {
	WithContext(ctx).Error(msg)
}

// Errorf logs a formatted error message with trace correlation
func Errorf(ctx context.Context, format string, args ...interface{}) {
	WithContext(ctx).Errorf(format, args...)
}

// Warn logs a warning message with trace correlation
func Warn(ctx context.Context, msg string) {
	WithContext(ctx).Warn(msg)
}

// Warnf logs a formatted warning message with trace correlation
func Warnf(ctx context.Context, format string, args ...interface{}) {
	WithContext(ctx).Warnf(format, args...)
}

// Debug logs a debug message with trace correlation
func Debug(ctx context.Context, msg string) {
	WithContext(ctx).Debug(msg)
}

// Debugf logs a formatted debug message with trace correlation
func Debugf(ctx context.Context, format string, args ...interface{}) {
	WithContext(ctx).Debugf(format, args...)
}

// WithFields returns a logger entry with additional custom fields
func WithFields(ctx context.Context, fields map[string]interface{}) *logrus.Entry {
	return WithContext(ctx).WithFields(fields)
}
