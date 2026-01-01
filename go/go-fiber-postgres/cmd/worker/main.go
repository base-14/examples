package main

import (
	"context"
	"fmt"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"

	"go-fiber-postgres/config"
	"go-fiber-postgres/internal/database"
	"go-fiber-postgres/internal/jobs"
	"go-fiber-postgres/internal/logging"
	"go-fiber-postgres/internal/telemetry"
)

func main() {
	ctx := context.Background()

	cfg := config.Load()

	serviceName := cfg.OTelConfig.ServiceName + "-worker"
	tel, err := telemetry.Init(ctx, serviceName, cfg.OTelConfig.OTLPEndpoint)
	if err != nil {
		fmt.Fprintf(os.Stderr, "failed to initialize telemetry: %v\n", err)
		os.Exit(1)
	}
	defer func() {
		shutdownCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		if err := tel.Shutdown(shutdownCtx); err != nil {
			logging.Error(ctx, "failed to shutdown telemetry", "error", err)
		}
	}()

	logging.Init(serviceName, cfg.Environment)

	db, err := database.Connect(ctx, cfg.DatabaseURL)
	if err != nil {
		logging.Error(ctx, "failed to connect to database", "error", err)
		os.Exit(1)
	}
	defer db.Close()

	if err := database.RunMigrations(ctx, db); err != nil {
		logging.Error(ctx, "failed to run migrations", "error", err)
		os.Exit(1)
	}

	pool, err := pgxpool.New(ctx, cfg.DatabaseURL)
	if err != nil {
		logging.Error(ctx, "failed to create pgxpool", "error", err)
		os.Exit(1)
	}
	defer pool.Close()

	if err := database.RunRiverMigrations(ctx, pool); err != nil {
		logging.Error(ctx, "failed to run river migrations", "error", err)
		os.Exit(1)
	}

	worker, err := jobs.NewWorker(ctx, pool)
	if err != nil {
		logging.Error(ctx, "failed to create worker", "error", err)
		os.Exit(1)
	}

	go func() {
		if err := worker.Start(ctx); err != nil {
			logging.Error(ctx, "worker error", "error", err)
		}
	}()

	logging.Info(ctx, "worker started")

	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
	<-quit

	logging.Info(ctx, "shutting down worker")

	shutdownCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	if err := worker.Stop(shutdownCtx); err != nil {
		logging.Error(ctx, "failed to stop worker", "error", err)
	}
}
