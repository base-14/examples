package main

import (
	"context"
	"fmt"
	"os"
	"os/signal"
	"syscall"
	"time"

	"go-echo-postgres/config"
	"go-echo-postgres/internal/database"
	"go-echo-postgres/internal/jobs"
	"go-echo-postgres/internal/logging"
	"go-echo-postgres/internal/telemetry"
)

func main() {
	ctx := context.Background()

	cfg, err := config.Load()
	if err != nil {
		fmt.Fprintf(os.Stderr, "failed to load config: %v\n", err)
		os.Exit(1)
	}

	logging.Init(cfg.IsDevelopment())

	serviceName := cfg.OTelServiceName + "-worker"
	shutdownTelemetry, err := telemetry.Init(ctx, serviceName, cfg.OTelEndpoint)
	if err != nil {
		logging.Logger().Fatal().Err(err).Msg("failed to initialize telemetry")
	}
	defer func() {
		shutdownCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		if err := shutdownTelemetry(shutdownCtx); err != nil {
			logging.Logger().Error().Err(err).Msg("failed to shutdown telemetry")
		}
	}()

	if err := database.Connect(cfg.DatabaseURL, cfg.IsDevelopment()); err != nil {
		logging.Logger().Fatal().Err(err).Msg("failed to initialize database")
	}
	defer database.Close()

	redisAddr := parseRedisAddr(cfg.RedisURL)
	server := jobs.NewServer(redisAddr, 10)

	go func() {
		if err := server.Start(); err != nil {
			logging.Logger().Fatal().Err(err).Msg("failed to start worker")
		}
	}()

	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
	<-quit

	logging.Logger().Info().Msg("shutting down worker")
	server.Shutdown()
}

func parseRedisAddr(redisURL string) string {
	if len(redisURL) > 8 && redisURL[:8] == "redis://" {
		return redisURL[8:]
	}
	return redisURL
}
