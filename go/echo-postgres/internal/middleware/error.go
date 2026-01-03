package middleware

import (
	"net/http"

	"go-echo-postgres/internal/logging"

	"github.com/labstack/echo/v4"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/codes"
	"go.opentelemetry.io/otel/trace"
)

type ErrorResponse struct {
	Error   string `json:"error"`
	TraceID string `json:"trace_id,omitempty"`
}

func ErrorHandler(err error, c echo.Context) {
	if c.Response().Committed {
		return
	}

	ctx := c.Request().Context()
	span := trace.SpanFromContext(ctx)

	span.RecordError(err)
	span.SetStatus(codes.Error, err.Error())

	var code int
	var message string

	if he, ok := err.(*echo.HTTPError); ok {
		code = he.Code
		if m, ok := he.Message.(string); ok {
			message = m
		} else {
			message = http.StatusText(he.Code)
		}
	} else {
		code = http.StatusInternalServerError
		message = "internal server error"
	}

	span.SetAttributes(attribute.Int("http.response.status_code", code))

	var traceID string
	if span.SpanContext().HasTraceID() {
		traceID = span.SpanContext().TraceID().String()
	}

	logging.Error(ctx).
		Err(err).
		Int("status", code).
		Msg("request error")

	response := ErrorResponse{
		Error:   message,
		TraceID: traceID,
	}

	if err := c.JSON(code, response); err != nil {
		logging.Error(ctx).Err(err).Msg("failed to write error response")
	}
}
