package activities

import (
	"context"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/trace"
)

func ValidateOrder(ctx context.Context, input ValidateOrderInput) (*ValidateOrderResult, error) {
	_, span := otel.Tracer("activities").Start(ctx, "validate_order",
		trace.WithAttributes(
			attribute.String("order.id", input.OrderID),
			attribute.String("customer.id", input.CustomerID),
			attribute.Float64("order.amount", input.TotalAmount),
			attribute.Int("order.item_count", len(input.Items)),
		),
	)
	defer span.End()

	if input.CustomerID == "" {
		span.SetAttributes(attribute.String("validation.failure", "missing_customer_id"))
		return &ValidateOrderResult{
			Valid:  false,
			Reason: "customer ID is required",
		}, nil
	}

	if len(input.Items) == 0 {
		span.SetAttributes(attribute.String("validation.failure", "no_items"))
		return &ValidateOrderResult{
			Valid:  false,
			Reason: "order must contain at least one item",
		}, nil
	}

	if input.TotalAmount <= 0 {
		span.SetAttributes(attribute.String("validation.failure", "invalid_amount"))
		return &ValidateOrderResult{
			Valid:  false,
			Reason: "order total must be greater than zero",
		}, nil
	}

	for _, item := range input.Items {
		if item.Quantity <= 0 {
			span.SetAttributes(attribute.String("validation.failure", "invalid_quantity"))
			return &ValidateOrderResult{
				Valid:  false,
				Reason: "item quantity must be greater than zero",
			}, nil
		}
	}

	span.SetAttributes(attribute.Bool("validation.passed", true))
	return &ValidateOrderResult{Valid: true}, nil
}
