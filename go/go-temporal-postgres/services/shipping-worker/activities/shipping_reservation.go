package activities

import (
	"context"
	"fmt"

	"github.com/google/uuid"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/trace"

	sharedactivities "github.com/base-14/examples/go/go-temporal-postgres/pkg/activities"
	"github.com/base-14/examples/go/go-temporal-postgres/pkg/simulation"
)

var simConfig simulation.Config

func InitSimulation() {
	simConfig = simulation.LoadConfig("SHIPPING")
}

func ReserveShipping(ctx context.Context, input sharedactivities.ShippingInput) (*sharedactivities.ShippingResult, error) {
	_, span := otel.Tracer("shipping-worker").Start(ctx, "reserve_shipping",
		trace.WithAttributes(
			attribute.String("order.id", input.OrderID),
			attribute.String("customer.id", input.CustomerID),
			attribute.Int("shipping.item_count", len(input.Items)),
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

	trackingID := fmt.Sprintf("TRK-%s", uuid.New().String()[:8])

	span.SetAttributes(
		attribute.Bool("shipping.reserved", true),
		attribute.String("shipping.tracking_id", trackingID),
	)

	return &sharedactivities.ShippingResult{
		Reserved:   true,
		TrackingID: trackingID,
	}, nil
}
