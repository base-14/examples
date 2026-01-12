package activities

import (
	"context"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/trace"
)

var mockInventory = map[string]int{
	"prod-1":            100,
	"prod-2":            50,
	"prod-3":            25,
	"out-of-stock-item": 0,
}

func InventoryCheck(ctx context.Context, input InventoryCheckInput) (*InventoryCheckResult, error) {
	_, span := otel.Tracer("activities").Start(ctx, "inventory_check",
		trace.WithAttributes(
			attribute.String("order.id", input.OrderID),
			attribute.Int("order.item_count", len(input.Items)),
		),
	)
	defer span.End()

	var unavailable []UnavailableItem
	for _, item := range input.Items {
		available, exists := mockInventory[item.ProductID]
		if !exists {
			available = 10
		}

		if available < item.Quantity {
			unavailable = append(unavailable, UnavailableItem{
				ProductID: item.ProductID,
				Requested: item.Quantity,
				Available: available,
			})
		}
	}

	allAvailable := len(unavailable) == 0
	span.SetAttributes(
		attribute.Bool("inventory.all_available", allAvailable),
		attribute.Int("inventory.unavailable_count", len(unavailable)),
	)

	return &InventoryCheckResult{
		AllAvailable:     allAvailable,
		UnavailableItems: unavailable,
	}, nil
}
