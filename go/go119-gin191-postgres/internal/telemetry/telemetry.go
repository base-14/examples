package telemetry

import (
	"context"
	"fmt"
	"log"
	"os"
	"time"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/exporters/otlp/otlpmetric/otlpmetricgrpc"
	"go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc"
	"go.opentelemetry.io/otel/propagation"
	"go.opentelemetry.io/otel/sdk/metric"
	"go.opentelemetry.io/otel/sdk/resource"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
	semconv "go.opentelemetry.io/otel/semconv/v1.17.0"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
)

type TelemetryProvider struct {
	TracerProvider *sdktrace.TracerProvider
	MeterProvider  *metric.MeterProvider
}

func InitTelemetry(ctx context.Context) (*TelemetryProvider, error) {
	serviceName := os.Getenv("OTEL_SERVICE_NAME")
	if serviceName == "" {
		serviceName = "go119-gin-app"
	}

	endpoint := os.Getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
	if endpoint == "" {
		endpoint = "localhost:4317"
	}

	environment := os.Getenv("OTEL_RESOURCE_ATTRIBUTES")
	if environment == "" {
		environment = "deployment.environment=development"
	}

	// Create resource with service information
	res, err := resource.New(ctx,
		resource.WithAttributes(
			semconv.ServiceName(serviceName),
			semconv.ServiceVersion("1.0.0"),
			attribute.String("deployment.environment", getEnvironment(environment)),
		),
	)
	if err != nil {
		return nil, fmt.Errorf("failed to create resource: %w", err)
	}

	// Setup trace provider
	traceProvider, err := setupTraceProvider(ctx, endpoint, res)
	if err != nil {
		return nil, fmt.Errorf("failed to setup trace provider: %w", err)
	}

	// Setup meter provider
	meterProvider, err := setupMeterProvider(ctx, endpoint, res)
	if err != nil {
		return nil, fmt.Errorf("failed to setup meter provider: %w", err)
	}

	// Set global propagator
	otel.SetTextMapPropagator(propagation.NewCompositeTextMapPropagator(
		propagation.TraceContext{},
		propagation.Baggage{},
	))

	log.Printf("OpenTelemetry initialized - Service: %s, Endpoint: %s", serviceName, endpoint)

	return &TelemetryProvider{
		TracerProvider: traceProvider,
		MeterProvider:  meterProvider,
	}, nil
}

func setupTraceProvider(ctx context.Context, endpoint string, res *resource.Resource) (*sdktrace.TracerProvider, error) {
	ctx, cancel := context.WithTimeout(ctx, 5*time.Second)
	defer cancel()

	conn, err := grpc.DialContext(ctx, endpoint,
		grpc.WithTransportCredentials(insecure.NewCredentials()),
		grpc.WithBlock(),
	)
	if err != nil {
		return nil, fmt.Errorf("failed to create gRPC connection to collector: %w", err)
	}

	traceExporter, err := otlptracegrpc.New(ctx, otlptracegrpc.WithGRPCConn(conn))
	if err != nil {
		return nil, fmt.Errorf("failed to create trace exporter: %w", err)
	}

	bsp := sdktrace.NewBatchSpanProcessor(traceExporter)
	tracerProvider := sdktrace.NewTracerProvider(
		sdktrace.WithSampler(sdktrace.AlwaysSample()),
		sdktrace.WithResource(res),
		sdktrace.WithSpanProcessor(bsp),
	)

	otel.SetTracerProvider(tracerProvider)
	return tracerProvider, nil
}

func setupMeterProvider(ctx context.Context, endpoint string, res *resource.Resource) (*metric.MeterProvider, error) {
	ctx, cancel := context.WithTimeout(ctx, 5*time.Second)
	defer cancel()

	conn, err := grpc.DialContext(ctx, endpoint,
		grpc.WithTransportCredentials(insecure.NewCredentials()),
		grpc.WithBlock(),
	)
	if err != nil {
		return nil, fmt.Errorf("failed to create gRPC connection to collector: %w", err)
	}

	metricExporter, err := otlpmetricgrpc.New(ctx, otlpmetricgrpc.WithGRPCConn(conn))
	if err != nil {
		return nil, fmt.Errorf("failed to create metric exporter: %w", err)
	}

	meterProvider := metric.NewMeterProvider(
		metric.WithReader(metric.NewPeriodicReader(metricExporter)),
		metric.WithResource(res),
	)

	otel.SetMeterProvider(meterProvider)
	return meterProvider, nil
}

func (tp *TelemetryProvider) Shutdown(ctx context.Context) error {
	if err := tp.TracerProvider.Shutdown(ctx); err != nil {
		return fmt.Errorf("error shutting down tracer provider: %w", err)
	}

	if err := tp.MeterProvider.Shutdown(ctx); err != nil {
		return fmt.Errorf("error shutting down meter provider: %w", err)
	}

	return nil
}

func getEnvironment(envAttr string) string {
	// Parse deployment.environment from OTEL_RESOURCE_ATTRIBUTES
	// Simple parser for "deployment.environment=value" format
	const prefix = "deployment.environment="
	if len(envAttr) > len(prefix) && envAttr[:len(prefix)] == prefix {
		return envAttr[len(prefix):]
	}
	return "development"
}
