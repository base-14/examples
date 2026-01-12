package activities

import (
	"context"
	"fmt"

	"github.com/google/uuid"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/trace"
)

func ReserveShipping(ctx context.Context, input ShippingInput) (*ShippingResult, error) {
	_, span := otel.Tracer("activities").Start(ctx, "reserve_shipping",
		trace.WithAttributes(
			attribute.String("order.id", input.OrderID),
			attribute.String("customer.id", input.CustomerID),
			attribute.Int("shipping.item_count", len(input.Items)),
		),
	)
	defer span.End()

	trackingID := fmt.Sprintf("TRK-%s", uuid.New().String()[:8])

	span.SetAttributes(
		attribute.Bool("shipping.reserved", true),
		attribute.String("shipping.tracking_id", trackingID),
	)

	return &ShippingResult{
		Reserved:   true,
		TrackingID: trackingID,
	}, nil
}
