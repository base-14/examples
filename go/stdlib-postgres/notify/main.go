package main

import (
	"context"
	"encoding/json"
	"errors"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp"
)

type payload struct {
	Event     string `json:"event"`
	ArticleID int64  `json:"article_id"`
	Title     string `json:"title"`
}

func main() {
	ctx := context.Background()

	port := envOr("NOTIFY_PORT", "8081")
	otlpEndpoint := envOr("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4318")
	serviceName := envOr("OTEL_SERVICE_NAME", "stdlib-notify")

	shutdownTel, err := initTelemetry(ctx, serviceName, otlpEndpoint)
	if err != nil {
		log.Fatalf("telemetry: %v", err)
	}
	defer func() {
		shutdownCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		if err := shutdownTel(shutdownCtx); err != nil {
			log.Printf("telemetry shutdown: %v", err)
		}
	}()

	logger := newLogger(serviceName)

	mux := http.NewServeMux()

	mux.HandleFunc("GET /api/health", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]string{
			"status":  "ok",
			"service": "stdlib-notify",
		})
	})

	mux.HandleFunc("POST /notify", func(w http.ResponseWriter, r *http.Request) {
		var p payload
		if err := json.NewDecoder(r.Body).Decode(&p); err != nil {
			logger.WarnContext(r.Context(), "Notification rejected: invalid payload", "error", err)
			http.Error(w, `{"error":"invalid payload"}`, http.StatusBadRequest)
			return
		}
		logger.InfoContext(r.Context(), "Notification received",
			"event", p.Event,
			"article_id", p.ArticleID,
			"title", p.Title,
		)
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]string{"status": "received"})
	})

	server := &http.Server{
		Addr: ":" + port,
		Handler: otelhttp.NewHandler(mux, "http.server",
			otelhttp.WithSpanNameFormatter(func(_ string, r *http.Request) string {
				return r.Method + " " + r.URL.Path
			}),
		),
		ReadHeaderTimeout: 5 * time.Second,
	}

	go func() {
		logger.Info("stdlib-notify listening", "port", port)
		if err := server.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			log.Fatalf("server error: %v", err)
		}
	}()

	sigCh := make(chan os.Signal, 1)
	signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM)
	<-sigCh

	shutdownCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	if err := server.Shutdown(shutdownCtx); err != nil {
		logger.Error("shutdown error", "error", err)
	}
}

func envOr(k, def string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return def
}
