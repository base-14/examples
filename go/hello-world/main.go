// Go Hello World — OpenTelemetry
package main

import (
	"context"
	"errors"
	"fmt"
	"os"
	"time"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/codes"
	"go.opentelemetry.io/otel/exporters/otlp/otlplog/otlploghttp"
	"go.opentelemetry.io/otel/exporters/otlp/otlpmetric/otlpmetrichttp"
	"go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracehttp"
	"go.opentelemetry.io/otel/log"
	"go.opentelemetry.io/otel/metric"
	sdklog "go.opentelemetry.io/otel/sdk/log"
	sdkmetric "go.opentelemetry.io/otel/sdk/metric"
	"go.opentelemetry.io/otel/sdk/resource"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
	semconv "go.opentelemetry.io/otel/semconv/v1.40.0"
	"go.opentelemetry.io/otel/trace"
)

func main() {
	// -- Configuration ------------------------------------------------------
	// The collector endpoint. Set this to where your OTel collector accepts
	// OTLP/HTTP traffic (default port 4318).
	endpoint := os.Getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
	if endpoint == "" {
		fmt.Println("Set OTEL_EXPORTER_OTLP_ENDPOINT (e.g. http://localhost:4318)")
		os.Exit(1)
	}

	ctx := context.Background()

	// A Resource identifies your application in the telemetry backend.
	// Every span, log, and metric carries this identity.
	// resource.Default() auto-populates host, OS, and process attributes.
	res, err := resource.Merge(
		resource.Default(),
		resource.NewWithAttributes(
			semconv.SchemaURL,
			semconv.ServiceName("hello-world-go"),
		),
	)
	if err != nil {
		fmt.Printf("Failed to create resource: %v\n", err)
		os.Exit(1)
	}

	// -- Traces -------------------------------------------------------------
	// A TracerProvider manages the lifecycle of traces. It batches spans and
	// sends them to the collector via the OTLP/HTTP exporter.
	traceExporter, err := otlptracehttp.New(ctx, otlptracehttp.WithEndpointURL(endpoint+"/v1/traces"))
	if err != nil {
		fmt.Printf("Failed to create trace exporter: %v\n", err)
		os.Exit(1)
	}
	tracerProvider := sdktrace.NewTracerProvider(
		sdktrace.WithResource(res),
		sdktrace.WithBatcher(traceExporter),
	)
	defer tracerProvider.Shutdown(ctx)
	otel.SetTracerProvider(tracerProvider)
	tracer := otel.Tracer("hello-world-go")

	// -- Logs ---------------------------------------------------------------
	// A LoggerProvider sends structured logs to the collector. Logs emitted
	// inside a span automatically carry the span's trace ID and span ID —
	// this is called log-trace correlation.
	logExporter, err := otlploghttp.New(ctx, otlploghttp.WithEndpointURL(endpoint+"/v1/logs"))
	if err != nil {
		fmt.Printf("Failed to create log exporter: %v\n", err)
		os.Exit(1)
	}
	loggerProvider := sdklog.NewLoggerProvider(
		sdklog.WithResource(res),
		sdklog.WithProcessor(sdklog.NewBatchProcessor(logExporter)),
	)
	defer loggerProvider.Shutdown(ctx)
	logger := loggerProvider.Logger("hello-world-go")

	// -- Metrics ------------------------------------------------------------
	// A MeterProvider manages metrics. The PeriodicReader collects and
	// exports metric data at regular intervals.
	metricExporter, err := otlpmetrichttp.New(ctx, otlpmetrichttp.WithEndpointURL(endpoint+"/v1/metrics"))
	if err != nil {
		fmt.Printf("Failed to create metric exporter: %v\n", err)
		os.Exit(1)
	}
	meterProvider := sdkmetric.NewMeterProvider(
		sdkmetric.WithResource(res),
		sdkmetric.WithReader(sdkmetric.NewPeriodicReader(metricExporter,
			sdkmetric.WithInterval(5*time.Second),
		)),
	)
	defer meterProvider.Shutdown(ctx)
	meter := meterProvider.Meter("hello-world-go")

	// A counter tracks how many times something happens.
	helloCounter, _ := meter.Int64Counter("hello.count",
		metric.WithDescription("Number of times the hello-world app has run"),
	)

	// -- Run ----------------------------------------------------------------
	sayHello(ctx, tracer, logger, helloCounter)
	checkDiskSpace(ctx, tracer, logger)
	parseConfig(ctx, tracer, logger)

	fmt.Println("Done. Check Scout for your trace, log, and metric.")
}

// sayHello is a normal operation — creates a span with an info log.
func sayHello(ctx context.Context, tracer trace.Tracer, logger log.Logger, counter metric.Int64Counter) {
	// A span represents a unit of work.
	ctx, span := tracer.Start(ctx, "say-hello")
	defer span.End()

	// This log is emitted inside the span, so it carries the span's trace ID.
	// In Scout, you can jump to the trace from a log detail.
	var rec log.Record
	rec.SetSeverityText("INFO")
	rec.SetSeverity(log.SeverityInfo)
	rec.SetBody(log.StringValue("Hello, World!"))
	logger.Emit(ctx, rec)

	counter.Add(ctx, 1)
	span.SetAttributes(attribute.String("greeting", "Hello, World!"))
}

// checkDiskSpace is a degraded operation — creates a span with a warning log.
func checkDiskSpace(ctx context.Context, tracer trace.Tracer, logger log.Logger) {
	ctx, span := tracer.Start(ctx, "check-disk-space")
	defer span.End()

	// Warnings show up in Scout with a distinct severity level, making
	// them easy to filter and spot before they become errors.
	var rec log.Record
	rec.SetSeverityText("WARN")
	rec.SetSeverity(log.SeverityWarn)
	rec.SetBody(log.StringValue("Disk usage above 90%"))
	logger.Emit(ctx, rec)

	span.SetAttributes(attribute.Int("disk.usage_percent", 92))
}

// parseConfig is a failed operation — creates a span with an error and exception.
func parseConfig(ctx context.Context, tracer trace.Tracer, logger log.Logger) {
	ctx, span := tracer.Start(ctx, "parse-config")
	defer span.End()

	err := errors.New("invalid config: missing 'database_url'")

	// RecordError attaches the stack trace to the span.
	// SetStatus marks the span as errored so it stands out in TraceX.
	span.RecordError(err)
	span.SetStatus(codes.Error, err.Error())

	var rec log.Record
	rec.SetSeverityText("ERROR")
	rec.SetSeverity(log.SeverityError)
	rec.SetBody(log.StringValue("Failed to parse configuration: " + err.Error()))
	logger.Emit(ctx, rec)
}
