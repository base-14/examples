package activities

import (
	"context"
	"log/slog"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/trace"
)

func SendConfirmation(ctx context.Context, input NotificationInput) error {
	_, span := otel.Tracer("activities").Start(ctx, "send_notification",
		trace.WithAttributes(
			attribute.String("order.id", input.OrderID),
			attribute.String("customer.id", input.CustomerID),
			attribute.String("notification.type", input.Type),
		),
	)
	defer span.End()

	slog.Info("notification sent",
		slog.String("order_id", input.OrderID),
		slog.String("customer_id", input.CustomerID),
		slog.String("type", input.Type),
		slog.String("message", input.Message),
	)

	span.SetAttributes(attribute.Bool("notification.sent", true))
	return nil
}
