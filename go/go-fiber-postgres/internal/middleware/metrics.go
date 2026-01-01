package middleware

import (
	"time"

	"github.com/gofiber/fiber/v2"
	"go.opentelemetry.io/otel/attribute"

	"go-fiber-postgres/internal/telemetry"
)

func Metrics() fiber.Handler {
	return func(c *fiber.Ctx) error {
		start := time.Now()

		err := c.Next()

		duration := float64(time.Since(start).Milliseconds())
		status := c.Response().StatusCode()
		method := c.Method()
		path := c.Route().Path

		attrs := []attribute.KeyValue{
			attribute.String("http.method", method),
			attribute.String("http.route", path),
			attribute.Int("http.status_code", status),
		}

		telemetry.HTTPRequestsTotal.Add(c.UserContext(), 1, telemetry.WithAttributes(attrs...))
		telemetry.HTTPRequestDuration.Record(c.UserContext(), duration, telemetry.WithAttributes(attrs...))

		return err
	}
}
