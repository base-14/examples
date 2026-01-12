package activities

import (
	"context"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/trace"

	sharedactivities "github.com/base-14/examples/go/go-temporal-postgres/pkg/activities"
	"github.com/base-14/examples/go/go-temporal-postgres/pkg/simulation"
)

var (
	mockInventory = map[string]int{
		"prod-1":            100,
		"prod-2":            50,
		"prod-3":            25,
		"out-of-stock-item": 0,
	}

	simConfig      simulation.Config
	outOfStockRate float64
)

func InitSimulation() {
	simConfig = simulation.LoadConfig("INVENTORY")
	outOfStockRate = simulation.LoadConfig("INVENTORY_OUT_OF_STOCK").FailureRate
	if outOfStockRate == 0 {
		outOfStockRate = 0.05
	}
}

func InventoryCheck(ctx context.Context, input sharedactivities.InventoryCheckInput) (*sharedactivities.InventoryCheckResult, error) {
	_, span := otel.Tracer("inventory-worker").Start(ctx, "inventory_check",
		trace.WithAttributes(
			attribute.String("order.id", input.OrderID),
			attribute.Int("order.item_count", len(input.Items)),
		),
	)
	defer span.End()

	if err := simulation.SimulateLatency(ctx, simConfig.MinLatencyMs, simConfig.MaxLatencyMs); err != nil {
		return nil, err
	}

	if simulation.ShouldFail(simConfig.FailureRate) {
		span.RecordError(simulation.ErrSimulatedFailure)
		return nil, simulation.ErrSimulatedFailure
	}

	var unavailable []sharedactivities.UnavailableItem
	for _, item := range input.Items {
		available, exists := mockInventory[item.ProductID]
		if !exists {
			available = 10
		}

		if simulation.ShouldFail(outOfStockRate) {
			available = 0
		}

		if available < item.Quantity {
			unavailable = append(unavailable, sharedactivities.UnavailableItem{
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

	return &sharedactivities.InventoryCheckResult{
		AllAvailable:     allAvailable,
		UnavailableItems: unavailable,
	}, nil
}
