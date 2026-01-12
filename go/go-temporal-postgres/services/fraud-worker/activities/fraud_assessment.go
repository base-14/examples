package activities

import (
	"context"
	"strings"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/trace"

	sharedactivities "github.com/base-14/examples/go/go-temporal-postgres/pkg/activities"
	"github.com/base-14/examples/go/go-temporal-postgres/pkg/simulation"
)

var simConfig simulation.Config

func InitSimulation() {
	simConfig = simulation.LoadConfig("FRAUD")
}

func FraudAssessment(ctx context.Context, input sharedactivities.FraudAssessmentInput) (*sharedactivities.FraudAssessmentResult, error) {
	_, span := otel.Tracer("fraud-worker").Start(ctx, "fraud_assessment",
		trace.WithAttributes(
			attribute.String("order.id", input.OrderID),
			attribute.String("customer.id", input.CustomerID),
			attribute.String("customer.tier", input.CustomerTier),
			attribute.Float64("order.amount", input.TotalAmount),
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

	riskScore := 0
	var reasons []string

	if strings.HasPrefix(input.CustomerID, "new-") {
		riskScore += 30
		reasons = append(reasons, "new_customer")
	}

	if input.CustomerTier == "new" || input.CustomerTier == "" {
		riskScore += 20
		reasons = append(reasons, "non_premium_tier")
	}

	if input.TotalAmount > 1000 {
		riskScore += 25
		reasons = append(reasons, "high_value_order")
	}

	if input.TotalAmount > 5000 {
		riskScore += 30
		reasons = append(reasons, "very_high_value_order")
	}

	if input.CustomerTier == "premium" {
		riskScore -= 20
		if riskScore < 0 {
			riskScore = 0
		}
	}

	span.SetAttributes(
		attribute.Int("fraud.risk_score", riskScore),
		attribute.Bool("fraud.high_risk", riskScore > 80),
		attribute.StringSlice("fraud.risk_factors", reasons),
	)

	return &sharedactivities.FraudAssessmentResult{
		RiskScore: riskScore,
		Reason:    strings.Join(reasons, ", "),
	}, nil
}
