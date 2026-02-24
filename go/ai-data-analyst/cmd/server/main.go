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
	pool, err := db.NewPool(ctx, cfg.DatabaseURL)
	if err != nil {
		log.Printf("WARNING: Database not available: %v", err)
		log.Printf("Running without database — /api/ask will not work")
		pool = nil
	}

	// LLM client
	var primary llm.Provider
	switch cfg.LLMProvider {
	case "ollama":
		primary = llm.NewOllamaProvider(cfg.OllamaBaseURL)
	case "google":
		primary = llm.NewGoogleProvider(cfg.GoogleAPIKey)
	default:
		primary = llm.NewOpenAIProvider(cfg.OpenAIAPIKey)
	}

	var fallback llm.Provider
	if cfg.FallbackProvider == "anthropic" && cfg.AnthropicAPIKey != "" {
		fallback = llm.NewAnthropicProvider(cfg.AnthropicAPIKey)
	}

	llmClient := &llm.Client{
		Primary:              primary,
		Fallback:             fallback,
		Tracer:               tp.Tracer,
		Metrics:              metrics,
		PrimaryProvider:      cfg.LLMProvider,
		FallbackProviderName: cfg.FallbackProvider,
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
		WriteTimeout: 60 * time.Second,
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
