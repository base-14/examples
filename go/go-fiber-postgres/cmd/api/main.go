package main

import (
	"context"
	"fmt"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/gofiber/contrib/otelfiber/v2"
	"github.com/gofiber/fiber/v2"
	"github.com/gofiber/fiber/v2/middleware/recover"
	"github.com/gofiber/fiber/v2/middleware/requestid"
	"github.com/jackc/pgx/v5/pgxpool"

	"go-fiber-postgres/config"
	"go-fiber-postgres/internal/database"
	"go-fiber-postgres/internal/handlers"
	"go-fiber-postgres/internal/jobs"
	"go-fiber-postgres/internal/logging"
	"go-fiber-postgres/internal/middleware"
	"go-fiber-postgres/internal/repository"
	"go-fiber-postgres/internal/services"
	"go-fiber-postgres/internal/telemetry"
)

func main() {
	ctx := context.Background()

	cfg := config.Load()

	tel, err := telemetry.Init(ctx, cfg.OTelConfig.ServiceName, cfg.OTelConfig.OTLPEndpoint)
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

	logging.Init(cfg.OTelConfig.ServiceName, cfg.Environment)

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

	jobClient, err := jobs.NewClient(ctx, pool)
	if err != nil {
		logging.Error(ctx, "failed to create job client", "error", err)
		os.Exit(1)
	}

	userRepo := repository.NewUserRepository(db)
	articleRepo := repository.NewArticleRepository(db)
	favoriteRepo := repository.NewFavoriteRepository(db)

	authService := services.NewAuthService(userRepo, cfg.JWTSecret, cfg.JWTExpiry)
	articleService := services.NewArticleService(articleRepo, favoriteRepo)

	healthHandler := handlers.NewHealthHandler(db)
	authHandler := handlers.NewAuthHandler(authService)
	articleHandler := handlers.NewArticleHandler(articleService, jobClient)

	authMiddleware := middleware.NewAuthMiddleware(authService)

	app := fiber.New(fiber.Config{
		DisableStartupMessage: true,
		ErrorHandler:          middleware.ErrorHandler,
	})

	app.Use(recover.New())
	app.Use(requestid.New())
	app.Use(otelfiber.Middleware())
	app.Use(middleware.Metrics())

	api := app.Group("/api")

	api.Get("/health", healthHandler.Check)

	api.Post("/register", authHandler.Register)
	api.Post("/login", authHandler.Login)

	api.Get("/user", authMiddleware.Required(), authHandler.GetUser)
	api.Post("/logout", authMiddleware.Required(), authHandler.Logout)

	api.Get("/articles", authMiddleware.Optional(), articleHandler.List)
	api.Get("/articles/:slug", authMiddleware.Optional(), articleHandler.Get)
	api.Post("/articles", authMiddleware.Required(), articleHandler.Create)
	api.Put("/articles/:slug", authMiddleware.Required(), articleHandler.Update)
	api.Delete("/articles/:slug", authMiddleware.Required(), articleHandler.Delete)
	api.Post("/articles/:slug/favorite", authMiddleware.Required(), articleHandler.Favorite)
	api.Delete("/articles/:slug/favorite", authMiddleware.Required(), articleHandler.Unfavorite)

	go func() {
		addr := fmt.Sprintf(":%s", cfg.Port)
		logging.Info(ctx, "starting server", "port", cfg.Port)
		if err := app.Listen(addr); err != nil {
			logging.Error(ctx, "server error", "error", err)
		}
	}()

	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
	<-quit

	logging.Info(ctx, "shutting down server")

	shutdownCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	if err := app.ShutdownWithContext(shutdownCtx); err != nil {
		logging.Error(ctx, "failed to shutdown server", "error", err)
	}
}
