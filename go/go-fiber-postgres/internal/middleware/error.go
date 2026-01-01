package middleware

import (
	"github.com/gofiber/fiber/v2"
	"go.opentelemetry.io/otel/trace"
)

func ErrorHandler(c *fiber.Ctx, err error) error {
	code := fiber.StatusInternalServerError

	if e, ok := err.(*fiber.Error); ok {
		code = e.Code
	}

	response := fiber.Map{
		"error": err.Error(),
	}

	span := trace.SpanFromContext(c.UserContext())
	if span.SpanContext().IsValid() {
		response["trace_id"] = span.SpanContext().TraceID().String()
	}

	return c.Status(code).JSON(response)
}

func ErrorResponse(c *fiber.Ctx, status int, message string) error {
	response := fiber.Map{
		"error": message,
	}

	span := trace.SpanFromContext(c.UserContext())
	if span.SpanContext().IsValid() {
		response["trace_id"] = span.SpanContext().TraceID().String()
	}

	return c.Status(status).JSON(response)
}
