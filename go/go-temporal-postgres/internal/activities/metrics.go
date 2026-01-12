package activities

import (
	"context"

	"github.com/base-14/examples/go/go-temporal-postgres/internal/telemetry"
)

type RecordMetricsInput struct {
	OrderID       string  `json:"order_id"`
	CustomerTier  string  `json:"customer_tier"`
	DecisionPath  string  `json:"decision_path"`
	RiskScore     int     `json:"risk_score"`
	DurationSecs  float64 `json:"duration_secs"`
	FailureReason string  `json:"failure_reason,omitempty"`
}

func RecordOrderMetrics(ctx context.Context, input RecordMetricsInput) error {
	telemetry.RecordOrderProcessed(ctx, input.CustomerTier)

	if input.RiskScore > 0 {
		telemetry.RecordFraudRiskScore(ctx, input.RiskScore, input.CustomerTier)
	}

	switch input.DecisionPath {
	case "auto_approved":
		telemetry.RecordOrderApproved(ctx, input.CustomerTier)
	case "manual_approved":
		telemetry.RecordOrderApproved(ctx, input.CustomerTier)
	case "manual_review":
		telemetry.RecordOrderManualReview(ctx, input.RiskScore)
	case "manual_rejected":
		telemetry.RecordOrderRejected(ctx, "manual_review_rejected")
	case "backorder":
		telemetry.RecordOrderBackordered(ctx)
	case "payment_declined", "payment_error":
		telemetry.RecordOrderPaymentFailed(ctx, input.FailureReason)
	case "validation_failed", "validation_error":
		telemetry.RecordOrderRejected(ctx, "validation_failed")
	case "fraud_error":
		telemetry.RecordOrderRejected(ctx, "fraud_check_error")
	case "inventory_error":
		telemetry.RecordOrderRejected(ctx, "inventory_check_error")
	}

	if input.DurationSecs > 0 {
		telemetry.RecordOrderProcessingDuration(ctx, input.DurationSecs, input.DecisionPath)
	}

	return nil
}
