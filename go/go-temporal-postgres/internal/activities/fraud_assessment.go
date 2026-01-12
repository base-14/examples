package activities

import (
	"context"
	"strings"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/trace"
)

func FraudAssessment(ctx context.Context, input FraudAssessmentInput) (*FraudAssessmentResult, error) {
	_, span := otel.Tracer("activities").Start(ctx, "fraud_assessment",
		trace.WithAttributes(
			attribute.String("order.id", input.OrderID),
			attribute.String("customer.id", input.CustomerID),
			attribute.String("customer.tier", input.CustomerTier),
			attribute.Float64("order.amount", input.TotalAmount),
		),
	)
	defer span.End()

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

	return &FraudAssessmentResult{
		RiskScore: riskScore,
		Reason:    strings.Join(reasons, ", "),
	}, nil
}
