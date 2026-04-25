package main

import (
	"context"
	"errors"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"stdlib-articles/handler"
	"stdlib-articles/middleware"
	"stdlib-articles/model"
	"stdlib-articles/repository"
	"stdlib-articles/service"

	"github.com/exaring/otelpgx"
	"github.com/jackc/pgx/v5/pgxpool"
	"go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp"
	"go.opentelemetry.io/otel"
)

func main() {
	ctx := context.Background()

	port := envOr("APP_PORT", "8080")
	dsn := envOr("DATABASE_URL", "postgres://postgres:postgres@db:5432/stdlib_articles?sslmode=disable")
	otlpEndpoint := envOr("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4318")
	notifyURL := envOr("NOTIFY_URL", "")
	serviceName := envOr("OTEL_SERVICE_NAME", "stdlib-articles")

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

	pool, err := newPool(ctx, dsn)
	if err != nil {
		log.Fatalf("db pool: %v", err)
	}
	defer pool.Close()

	if _, err := pool.Exec(ctx, model.Schema); err != nil {
		log.Fatalf("schema: %v", err)
	}

	logger := middleware.NewLogger(serviceName)

	createdCounter, err := otel.Meter("stdlib-articles").Int64Counter("articles.created")
	if err != nil {
		log.Fatalf("counter: %v", err)
	}

	notifier := service.NewNotifier(notifyURL)
	repo := repository.NewArticleRepository(pool)
	articles := handler.NewArticleHandler(repo, notifier.NotifyArticleCreated, logger, createdCounter)

	logger.Info("stdlib-articles starting", "port", port)

	mux := http.NewServeMux()
	mux.HandleFunc("GET /api/health", handler.Health)
	articles.Register(mux)

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
		log.Printf("stdlib-articles listening on :%s", port)
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
		log.Printf("shutdown error: %v", err)
	}
}

func newPool(ctx context.Context, dsn string) (*pgxpool.Pool, error) {
	cfg, err := pgxpool.ParseConfig(dsn)
	if err != nil {
		return nil, err
	}
	cfg.ConnConfig.Tracer = otelpgx.NewTracer()

	pool, err := pgxpool.NewWithConfig(ctx, cfg)
	if err != nil {
		return nil, err
	}

	pingCtx, cancel := context.WithTimeout(ctx, 10*time.Second)
	defer cancel()
	if err := pool.Ping(pingCtx); err != nil {
		pool.Close()
		return nil, err
	}
	return pool, nil
}

func envOr(k, def string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return def
}
