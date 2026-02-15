package main

import (
	"context"
	"fmt"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"go-echo-postgres/config"
	"go-echo-postgres/internal/database"
	"go-echo-postgres/internal/handlers"
	"go-echo-postgres/internal/jobs"
	"go-echo-postgres/internal/logging"
	"go-echo-postgres/internal/middleware"
	"go-echo-postgres/internal/services"
	"go-echo-postgres/internal/telemetry"

	"github.com/labstack/echo/v4"
	echomiddleware "github.com/labstack/echo/v4/middleware"
	"go.opentelemetry.io/contrib/instrumentation/github.com/labstack/echo/otelecho"
)

func main() {
	ctx := context.Background()

	cfg, err := config.Load()
	if err != nil {
		fmt.Fprintf(os.Stderr, "failed to load config: %v\n", err)
		os.Exit(1)
	}

	logging.Init(cfg.IsDevelopment())

	shutdownTelemetry, err := telemetry.Init(ctx, cfg.OTelServiceName, cfg.OTelEndpoint)
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

	if err := middleware.InitMetrics(); err != nil {
		logging.Logger().Fatal().Err(err).Msg("failed to initialize metrics")
	}

	if err := database.Connect(cfg.DatabaseURL, cfg.IsDevelopment()); err != nil {
		logging.Logger().Fatal().Err(err).Msg("failed to initialize database")
	}
	defer database.Close()

	if err := database.Migrate(); err != nil {
		logging.Logger().Fatal().Err(err).Msg("failed to run database migrations")
	}

	redisAddr := parseRedisAddr(cfg.RedisURL)
	jobClient, err := jobs.NewClient(redisAddr)
	if err != nil {
		logging.Logger().Fatal().Err(err).Msg("failed to create job client")
	}
	defer jobClient.Close()

	userService := services.NewUserService()
	authService := services.NewAuthService(cfg.JWTSecret, cfg.JWTExpiresIn)
	articleService := services.NewArticleService()

	healthHandler := handlers.NewHealthHandler(redisAddr)
	authHandler := handlers.NewAuthHandler(authService, userService)
	articleHandler := handlers.NewArticleHandler(articleService, jobClient)

	e := echo.New()
	e.HideBanner = true

	e.Use(echomiddleware.Recover())
	e.Use(echomiddleware.RequestID())
	e.Use(otelecho.Middleware(cfg.OTelServiceName, otelecho.WithSkipper(func(c echo.Context) bool {
		return c.Path() == "/api/health"
	})))
	e.Use(middleware.Metrics())
	e.HTTPErrorHandler = middleware.ErrorHandler

	if cfg.IsDevelopment() {
		e.Use(echomiddleware.Logger())
	}

	api := e.Group("/api")

	api.GET("/health", healthHandler.Check)

	api.POST("/register", authHandler.Register)
	api.POST("/login", authHandler.Login)

	auth := api.Group("")
	auth.Use(middleware.JWTAuth(cfg.JWTSecret))
	auth.GET("/user", authHandler.GetCurrentUser)
	auth.POST("/logout", authHandler.Logout)

	api.GET("/articles", articleHandler.List, middleware.OptionalJWTAuth(cfg.JWTSecret))
	api.GET("/articles/:slug", articleHandler.Get, middleware.OptionalJWTAuth(cfg.JWTSecret))

	authArticles := api.Group("/articles")
	authArticles.Use(middleware.JWTAuth(cfg.JWTSecret))
	authArticles.POST("", articleHandler.Create)
	authArticles.PUT("/:slug", articleHandler.Update)
	authArticles.DELETE("/:slug", articleHandler.Delete)
	authArticles.POST("/:slug/favorite", articleHandler.Favorite)
	authArticles.DELETE("/:slug/favorite", articleHandler.Unfavorite)

	go func() {
		addr := fmt.Sprintf(":%s", cfg.Port)
		logging.Logger().Info().Str("port", cfg.Port).Msg("starting server")
		if err := e.Start(addr); err != nil && err != http.ErrServerClosed {
			logging.Logger().Fatal().Err(err).Msg("server error")
		}
	}()

	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
	<-quit

	logging.Logger().Info().Msg("shutting down server")

	shutdownCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	if err := e.Shutdown(shutdownCtx); err != nil {
		logging.Logger().Error().Err(err).Msg("failed to shutdown server")
	}
}

func parseRedisAddr(redisURL string) string {
	if len(redisURL) > 8 && redisURL[:8] == "redis://" {
		return redisURL[8:]
	}
	return redisURL
}
