package main

import (
	"context"
	"fmt"
	"log/slog"
	"os"
	"os/signal"
	"syscall"

	"github.com/base-14/examples/go/go-temporal-postgres/pkg/telemetry"
	pkgtemporal "github.com/base-14/examples/go/go-temporal-postgres/pkg/temporal"
	"github.com/base-14/examples/go/go-temporal-postgres/services/notification-worker/activities"
)

func main() {
	if err := run(); err != nil {
		slog.Error("application error", slog.String("error", err.Error()))
		os.Exit(1)
	}
}

func run() error {
	ctx := context.Background()

	serviceName := getEnv("OTEL_SERVICE_NAME", "notification-worker")
	environment := getEnv("ENVIRONMENT", "development")
	otelEndpoint := getEnv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4318")
	temporalHost := getEnv("TEMPORAL_HOST", "temporal:7233")
	taskQueue := getEnv("TASK_QUEUE", "notification-queue")

	shutdownTelemetry, err := telemetry.Init(ctx, telemetry.Config{
		ServiceName:    serviceName,
		ServiceVersion: "1.0.0",
		Environment:    environment,
		Endpoint:       otelEndpoint,
	})
	if err != nil {
		return fmt.Errorf("failed to initialize telemetry: %w", err)
	}
	defer func() {
		if err := shutdownTelemetry(ctx); err != nil {
			slog.Error("failed to shutdown telemetry", slog.String("error", err.Error()))
		}
	}()

	temporalClient, err := pkgtemporal.NewClient(pkgtemporal.ClientConfig{
		HostPort: temporalHost,
	})
	if err != nil {
		return fmt.Errorf("failed to create Temporal client: %w", err)
	}
	defer temporalClient.Close()

	w, err := pkgtemporal.NewWorker(temporalClient, pkgtemporal.WorkerConfig{
		TaskQueue: taskQueue,
	})
	if err != nil {
		return fmt.Errorf("failed to create Temporal worker: %w", err)
	}

	activities.InitSimulation()
	w.RegisterActivity(activities.SendConfirmation)

	slog.Info("starting Notification worker",
		slog.String("temporal_host", temporalHost),
		slog.String("task_queue", taskQueue),
		slog.String("environment", environment),
	)

	workerErr := make(chan error, 1)
	go func() {
		if err := w.Run(nil); err != nil {
			workerErr <- err
		}
	}()

	sigCh := make(chan os.Signal, 1)
	signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM)

	slog.Info("notification worker is running, waiting for tasks...")

	select {
	case err := <-workerErr:
		return fmt.Errorf("worker error: %w", err)
	case <-sigCh:
	}

	slog.Info("shutting down notification worker")
	w.Stop()

	return nil
}

func getEnv(key, defaultValue string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return defaultValue
}
