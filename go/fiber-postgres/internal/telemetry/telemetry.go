package telemetry

import (
	"context"
	"time"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/exporters/otlp/otlplog/otlploghttp"
	"go.opentelemetry.io/otel/exporters/otlp/otlpmetric/otlpmetrichttp"
	"go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracehttp"
	"go.opentelemetry.io/otel/log/global"
	"go.opentelemetry.io/otel/metric"
	"go.opentelemetry.io/otel/propagation"
	sdklog "go.opentelemetry.io/otel/sdk/log"
	sdkmetric "go.opentelemetry.io/otel/sdk/metric"
	"go.opentelemetry.io/otel/sdk/resource"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
	semconv "go.opentelemetry.io/otel/semconv/v1.24.0"
	"go.opentelemetry.io/otel/trace"
)

var (
	tracer trace.Tracer
	meter  metric.Meter

	ArticlesCreated  metric.Int64Counter
	ArticlesDeleted  metric.Int64Counter
	FavoritesAdded   metric.Int64Counter
	FavoritesRemoved metric.Int64Counter
	JobsEnqueued     metric.Int64Counter
	JobsCompleted    metric.Int64Counter
	JobsFailed       metric.Int64Counter

	HTTPRequestsTotal   metric.Int64Counter
	HTTPRequestDuration metric.Float64Histogram
)

type Telemetry struct {
	TracerProvider *sdktrace.TracerProvider
	MeterProvider  *sdkmetric.MeterProvider
	LoggerProvider *sdklog.LoggerProvider
}

func Init(ctx context.Context, serviceName, otlpEndpoint string) (*Telemetry, error) {
	res, err := resource.New(ctx,
		resource.WithAttributes(
			semconv.ServiceNameKey.String(serviceName),
			semconv.ServiceVersionKey.String("1.0.0"),
		),
	)
	if err != nil {
		return nil, err
	}

	traceExporter, err := otlptracehttp.New(ctx,
		otlptracehttp.WithEndpoint(trimHTTP(otlpEndpoint)),
		otlptracehttp.WithInsecure(),
	)
	if err != nil {
		return nil, err
	}

	tp := sdktrace.NewTracerProvider(
		sdktrace.WithBatcher(traceExporter),
		sdktrace.WithResource(res),
	)
	otel.SetTracerProvider(tp)
	otel.SetTextMapPropagator(propagation.NewCompositeTextMapPropagator(
		propagation.TraceContext{},
		propagation.Baggage{},
	))

	metricExporter, err := otlpmetrichttp.New(ctx,
		otlpmetrichttp.WithEndpoint(trimHTTP(otlpEndpoint)),
		otlpmetrichttp.WithInsecure(),
	)
	if err != nil {
		return nil, err
	}

	mp := sdkmetric.NewMeterProvider(
		sdkmetric.WithReader(sdkmetric.NewPeriodicReader(metricExporter, sdkmetric.WithInterval(15*time.Second))),
		sdkmetric.WithResource(res),
	)
	otel.SetMeterProvider(mp)

	logExporter, err := otlploghttp.New(ctx,
		otlploghttp.WithEndpoint(trimHTTP(otlpEndpoint)),
		otlploghttp.WithInsecure(),
	)
	if err != nil {
		return nil, err
	}

	lp := sdklog.NewLoggerProvider(
		sdklog.WithProcessor(sdklog.NewBatchProcessor(logExporter)),
		sdklog.WithResource(res),
	)
	global.SetLoggerProvider(lp)

	tracer = tp.Tracer(serviceName)
	meter = mp.Meter(serviceName)

	if err := initMetrics(); err != nil {
		return nil, err
	}

	return &Telemetry{
		TracerProvider: tp,
		MeterProvider:  mp,
		LoggerProvider: lp,
	}, nil
}

func initMetrics() error {
	var err error

	ArticlesCreated, err = meter.Int64Counter("articles.created",
		metric.WithDescription("Total number of articles created"))
	if err != nil {
		return err
	}

	ArticlesDeleted, err = meter.Int64Counter("articles.deleted",
		metric.WithDescription("Total number of articles deleted"))
	if err != nil {
		return err
	}

	FavoritesAdded, err = meter.Int64Counter("favorites.added",
		metric.WithDescription("Total number of favorites added"))
	if err != nil {
		return err
	}

	FavoritesRemoved, err = meter.Int64Counter("favorites.removed",
		metric.WithDescription("Total number of favorites removed"))
	if err != nil {
		return err
	}

	JobsEnqueued, err = meter.Int64Counter("jobs.enqueued",
		metric.WithDescription("Total number of jobs enqueued"))
	if err != nil {
		return err
	}

	JobsCompleted, err = meter.Int64Counter("jobs.completed",
		metric.WithDescription("Total number of jobs completed"))
	if err != nil {
		return err
	}

	JobsFailed, err = meter.Int64Counter("jobs.failed",
		metric.WithDescription("Total number of jobs failed"))
	if err != nil {
		return err
	}

	HTTPRequestsTotal, err = meter.Int64Counter("http.requests.total",
		metric.WithDescription("Total number of HTTP requests"),
		metric.WithUnit("{request}"))
	if err != nil {
		return err
	}

	HTTPRequestDuration, err = meter.Float64Histogram("http.request.duration",
		metric.WithDescription("HTTP request duration in milliseconds"),
		metric.WithUnit("ms"),
		metric.WithExplicitBucketBoundaries(1, 5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000))
	if err != nil {
		return err
	}

	return nil
}

func Tracer() trace.Tracer {
	return tracer
}

func Meter() metric.Meter {
	return meter
}

func WithAttributes(attrs ...attribute.KeyValue) metric.MeasurementOption {
	return metric.WithAttributes(attrs...)
}

func (t *Telemetry) Shutdown(ctx context.Context) error {
	if err := t.TracerProvider.Shutdown(ctx); err != nil {
		return err
	}
	if err := t.MeterProvider.Shutdown(ctx); err != nil {
		return err
	}
	if t.LoggerProvider != nil {
		return t.LoggerProvider.Shutdown(ctx)
	}
	return nil
}

func trimHTTP(endpoint string) string {
	if len(endpoint) > 7 && endpoint[:7] == "http://" {
		return endpoint[7:]
	}
	if len(endpoint) > 8 && endpoint[:8] == "https://" {
		return endpoint[8:]
	}
	return endpoint
}
