package main

import (
	"context"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"ai-data-analyst/internal/config"
	"ai-data-analyst/internal/db"
	"ai-data-analyst/internal/llm"
	"ai-data-analyst/internal/middleware"
	"ai-data-analyst/internal/pipeline"
	"ai-data-analyst/internal/routes"
	"ai-data-analyst/internal/telemetry"

	"github.com/go-chi/chi/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

const (
	dbConnectWindow   = 30 * time.Second
	dbConnectInterval = 2 * time.Second
)

func main() {
	cfg := config.Load()
	ctx := context.Background()

	// Telemetry
	tp, err := telemetry.Init(ctx, cfg.OTelServiceName, cfg.OTelEndpoint, cfg.ScoutEnvironment)
	if err != nil {
		log.Fatalf("Failed to init telemetry: %v", err)
	}

	metrics, err := telemetry.NewGenAIMetrics(tp.Meter)
	if err != nil {
		log.Fatalf("Failed to init metrics: %v", err)
	}

	// Database
	pool, err := connectWithRetry(ctx, cfg.DatabaseURL)
	if err != nil {
		log.Printf("WARNING: Database not available: %v", err)
		log.Printf("Running without database - /api/ask will not work")
		pool = nil
	}

	// LLM client
	primary, err := llm.NewProvider(cfg.LLMProvider, cfg)
	if err != nil {
		log.Fatalf("Failed to create primary provider: %v", err)
	}

	fallback, err := llm.NewProvider(cfg.FallbackProvider, cfg)
	if err != nil {
		log.Fatalf("Failed to create fallback provider: %v", err)
	}

	llmClient := &llm.Client{
		Primary:        primary,
		Fallback:       fallback,
		FallbackModel:  cfg.FallbackModel,
		Tracer:         tp.Tracer,
		Metrics:        metrics,
		CaptureContent: cfg.CaptureContent,
	}

	// Pipeline
	p := &pipeline.Pipeline{
		LLM:     llmClient,
		Tracer:  tp.Tracer,
		Metrics: metrics,
		Config:  cfg,
	}
	if pool != nil {
		p.DB = pool
	}

	// Router
	r := chi.NewRouter()
	r.Use(middleware.OTelHTTP(cfg.OTelServiceName))
	r.Use(middleware.ErrorStatus)
	r.Use(middleware.Recovery)

	r.Get("/api/health", routes.HealthHandler(cfg.OTelServiceName))
	r.Get("/api/schema", routes.SchemaHandler())
	r.Post("/api/ask", routes.AskHandler(p))

	if pool != nil {
		r.Get("/api/history", routes.HistoryHandler(pool))
		r.Get("/api/indicators", routes.IndicatorsHandler(pool))
	}

	srv := &http.Server{
		Addr:         ":" + cfg.Port,
		Handler:      r,
		ReadTimeout:  30 * time.Second,
		WriteTimeout: 300 * time.Second,
		IdleTimeout:  60 * time.Second,
	}

	go func() {
		log.Printf("Starting %s on :%s", cfg.OTelServiceName, cfg.Port)
		if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatalf("Server error: %v", err)
		}
	}()

	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, syscall.SIGINT, syscall.SIGTERM)
	<-sigChan

	log.Println("Shutting down...")
	shutdownCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	if err := srv.Shutdown(shutdownCtx); err != nil {
		log.Printf("Server shutdown error: %v", err)
	}
	if pool != nil {
		pool.Close()
	}
	if err := tp.Shutdown(shutdownCtx); err != nil {
		log.Printf("Telemetry shutdown error: %v", err)
	}
}

// connectWithRetry keeps trying the database for dbConnectWindow, because the
// postgres image restarts its server after first-time initialisation and can
// refuse connections just after its readiness probe passes.
func connectWithRetry(ctx context.Context, databaseURL string) (*pgxpool.Pool, error) {
	return retryConnect(ctx, databaseURL, db.NewPool, dbConnectWindow, dbConnectInterval)
}

type poolDialer func(ctx context.Context, databaseURL string) (*pgxpool.Pool, error)

func retryConnect(ctx context.Context, databaseURL string, dial poolDialer, window, interval time.Duration) (*pgxpool.Pool, error) {
	deadline := time.Now().Add(window)
	for {
		pool, err := dial(ctx, databaseURL)
		if err == nil || time.Now().After(deadline) {
			return pool, err
		}
		log.Printf("Database not ready, retrying in %s: %v", interval, err)
		time.Sleep(interval)
	}
}
