package activities

import (
	"context"
	"log/slog"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/trace"

	sharedactivities "github.com/base-14/examples/go/go-temporal-postgres/pkg/activities"
	"github.com/base-14/examples/go/go-temporal-postgres/pkg/simulation"
)

var simConfig simulation.Config

func InitSimulation() {
	simConfig = simulation.LoadConfig("NOTIFICATION")
}

func SendConfirmation(ctx context.Context, input sharedactivities.NotificationInput) error {
	_, span := otel.Tracer("notification-worker").Start(ctx, "send_notification",
		trace.WithAttributes(
			attribute.String("order.id", input.OrderID),
			attribute.String("customer.id", input.CustomerID),
			attribute.String("notification.type", input.Type),
		),
	)
	defer span.End()

	if err := simulation.SimulateLatency(ctx, simConfig.MinLatencyMs, simConfig.MaxLatencyMs); err != nil {
		return err
	}

	if simulation.ShouldFail(simConfig.FailureRate) {
		span.RecordError(simulation.ErrSimulatedFailure)
		return simulation.ErrSimulatedFailure
	}

	slog.Info("notification sent",
		slog.String("order_id", input.OrderID),
		slog.String("customer_id", input.CustomerID),
		slog.String("type", input.Type),
		slog.String("message", input.Message),
	)

	span.SetAttributes(attribute.Bool("notification.sent", true))
	return nil
}
