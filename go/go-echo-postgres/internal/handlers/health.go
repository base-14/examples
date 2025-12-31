package handlers

import (
	"context"
	"net/http"
	"time"

	"go-echo-postgres/internal/database"

	"github.com/hibiken/asynq"
	"github.com/labstack/echo/v4"
)

type HealthHandler struct {
	redisAddr string
}

func NewHealthHandler(redisAddr string) *HealthHandler {
	return &HealthHandler{redisAddr: redisAddr}
}

type HealthResponse struct {
	Status   string            `json:"status"`
	Database string            `json:"database"`
	Redis    string            `json:"redis"`
	Details  map[string]string `json:"details,omitempty"`
}

func (h *HealthHandler) Check(c echo.Context) error {
	ctx := c.Request().Context()

	dbStatus := "healthy"
	if err := database.CheckHealth(); err != nil {
		dbStatus = "unhealthy"
	}

	redisStatus := "healthy"
	if err := h.checkRedis(ctx); err != nil {
		redisStatus = "unhealthy"
	}

	overallStatus := "healthy"
	statusCode := http.StatusOK
	if dbStatus != "healthy" || redisStatus != "healthy" {
		overallStatus = "degraded"
		statusCode = http.StatusServiceUnavailable
	}

	response := HealthResponse{
		Status:   overallStatus,
		Database: dbStatus,
		Redis:    redisStatus,
	}

	return c.JSON(statusCode, response)
}

func (h *HealthHandler) checkRedis(ctx context.Context) error {
	inspector := asynq.NewInspector(asynq.RedisClientOpt{Addr: h.redisAddr})
	defer inspector.Close()

	ctx, cancel := context.WithTimeout(ctx, 2*time.Second)
	defer cancel()

	done := make(chan error, 1)
	go func() {
		_, err := inspector.Queues()
		done <- err
	}()

	select {
	case err := <-done:
		return err
	case <-ctx.Done():
		return ctx.Err()
	}
}
