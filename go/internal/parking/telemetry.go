package parking

import (
	"context"
	"os"
	"time"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/exporters/otlp/otlpmetric/otlpmetrichttp"
	"go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracehttp"
	"go.opentelemetry.io/otel/metric"
	"go.opentelemetry.io/otel/propagation"
	sdkmetric "go.opentelemetry.io/otel/sdk/metric"
	"go.opentelemetry.io/otel/sdk/resource"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
	semconv "go.opentelemetry.io/otel/semconv/v1.21.0"
	"go.opentelemetry.io/otel/trace"
)

const (
	defaultServiceName  = "parking-lot-service"
	serviceVersion      = "1.0.0"
	defaultOTLPEndpoint = "http://localhost:4318"
)

type TelemetryProvider struct {
	tracerProvider *sdktrace.TracerProvider
	meterProvider  *sdkmetric.MeterProvider
	tracer         trace.Tracer
	meter          metric.Meter
}

func NewTelemetryProvider() (*TelemetryProvider, error) {
	ctx := context.Background()

	serviceName := os.Getenv("OTEL_SERVICE_NAME")
	if serviceName == "" {
		serviceName = defaultServiceName
	}

	otlpEndpoint := os.Getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
	if otlpEndpoint == "" {
		otlpEndpoint = defaultOTLPEndpoint
	}

	resAttrs := []resource.Option{
		resource.WithAttributes(
			semconv.ServiceName(serviceName),
			semconv.ServiceVersion(serviceVersion),
		),
	}

	if resAttrStr := os.Getenv("OTEL_RESOURCE_ATTRIBUTES"); resAttrStr != "" {
		resAttrs = append(resAttrs, resource.WithFromEnv())
	}

	resource, err := resource.New(ctx, resAttrs...)
	if err != nil {
		return nil, err
	}

	// Setup trace exporter
	traceExporter, err := otlptracehttp.New(ctx,
		otlptracehttp.WithEndpointURL(otlpEndpoint+"/v1/traces"),
		otlptracehttp.WithInsecure(), // Use for local development
	)
	if err != nil {
		return nil, err
	}

	tracerProvider := sdktrace.NewTracerProvider(
		sdktrace.WithBatcher(traceExporter),
		sdktrace.WithResource(resource),
		sdktrace.WithSampler(sdktrace.AlwaysSample()),
	)

	// Setup metric exporter
	metricExporter, err := otlpmetrichttp.New(ctx,
		otlpmetrichttp.WithEndpointURL(otlpEndpoint+"/v1/metrics"),
		otlpmetrichttp.WithInsecure(), // Use for local development
	)
	if err != nil {
		return nil, err
	}

	meterProvider := sdkmetric.NewMeterProvider(
		sdkmetric.WithResource(resource),
		sdkmetric.WithReader(sdkmetric.NewPeriodicReader(metricExporter,
			sdkmetric.WithInterval(5*time.Second), // Export every 5 seconds
		)),
	)

	// Set global providers
	otel.SetTracerProvider(tracerProvider)
	otel.SetMeterProvider(meterProvider)

	// Set global propagator to tracecontext and baggage
	otel.SetTextMapPropagator(propagation.NewCompositeTextMapPropagator(
		propagation.TraceContext{},
		propagation.Baggage{},
	))

	tracer := otel.Tracer(serviceName)
	meter := otel.Meter(serviceName)

	return &TelemetryProvider{
		tracerProvider: tracerProvider,
		meterProvider:  meterProvider,
		tracer:         tracer,
		meter:          meter,
	}, nil
}

func (tp *TelemetryProvider) Tracer() trace.Tracer {
	return tp.tracer
}

func (tp *TelemetryProvider) Meter() metric.Meter {
	return tp.meter
}

func (tp *TelemetryProvider) Shutdown(ctx context.Context) error {
	if err := tp.tracerProvider.Shutdown(ctx); err != nil {
		return err
	}
	return tp.meterProvider.Shutdown(ctx)
}
