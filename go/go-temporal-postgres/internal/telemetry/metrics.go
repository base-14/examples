package telemetry

import (
	"context"
	"sync"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/metric"
)

var (
	meter       metric.Meter
	metricsOnce sync.Once

	ordersProcessed     metric.Int64Counter
	ordersApproved      metric.Int64Counter
	ordersRejected      metric.Int64Counter
	ordersManualReview  metric.Int64Counter
	ordersBackordered   metric.Int64Counter
	ordersPaymentFailed metric.Int64Counter

	orderProcessingDuration metric.Float64Histogram
	fraudRiskScore          metric.Int64Histogram
)

func initMetrics() {
	meter = otel.Meter("order-fulfillment")

	var err error

	ordersProcessed, err = meter.Int64Counter("orders.processed",
		metric.WithDescription("Total number of orders processed"),
		metric.WithUnit("{order}"),
	)
	if err != nil {
		panic(err)
	}

	ordersApproved, err = meter.Int64Counter("orders.approved",
		metric.WithDescription("Number of orders auto-approved"),
		metric.WithUnit("{order}"),
	)
	if err != nil {
		panic(err)
	}

	ordersRejected, err = meter.Int64Counter("orders.rejected",
		metric.WithDescription("Number of orders rejected"),
		metric.WithUnit("{order}"),
	)
	if err != nil {
		panic(err)
	}

	ordersManualReview, err = meter.Int64Counter("orders.manual_review",
		metric.WithDescription("Number of orders sent to manual review"),
		metric.WithUnit("{order}"),
	)
	if err != nil {
		panic(err)
	}

	ordersBackordered, err = meter.Int64Counter("orders.backordered",
		metric.WithDescription("Number of orders placed on backorder"),
		metric.WithUnit("{order}"),
	)
	if err != nil {
		panic(err)
	}

	ordersPaymentFailed, err = meter.Int64Counter("orders.payment_failed",
		metric.WithDescription("Number of orders with payment failures"),
		metric.WithUnit("{order}"),
	)
	if err != nil {
		panic(err)
	}

	orderProcessingDuration, err = meter.Float64Histogram("orders.processing_duration",
		metric.WithDescription("Order processing duration in seconds"),
		metric.WithUnit("s"),
		metric.WithExplicitBucketBoundaries(0.1, 0.5, 1, 2, 5, 10, 30, 60, 120),
	)
	if err != nil {
		panic(err)
	}

	fraudRiskScore, err = meter.Int64Histogram("orders.fraud_risk_score",
		metric.WithDescription("Distribution of fraud risk scores"),
		metric.WithUnit("{score}"),
		metric.WithExplicitBucketBoundaries(0, 20, 40, 60, 80, 100),
	)
	if err != nil {
		panic(err)
	}
}

func ensureMetrics() {
	metricsOnce.Do(initMetrics)
}

func RecordOrderProcessed(ctx context.Context, customerTier string) {
	ensureMetrics()
	ordersProcessed.Add(ctx, 1, metric.WithAttributes(
		attribute.String("customer_tier", customerTier),
	))
}

func RecordOrderApproved(ctx context.Context, customerTier string) {
	ensureMetrics()
	ordersApproved.Add(ctx, 1, metric.WithAttributes(
		attribute.String("customer_tier", customerTier),
	))
}

func RecordOrderRejected(ctx context.Context, reason string) {
	ensureMetrics()
	ordersRejected.Add(ctx, 1, metric.WithAttributes(
		attribute.String("reason", reason),
	))
}

func RecordOrderManualReview(ctx context.Context, riskScore int) {
	ensureMetrics()
	ordersManualReview.Add(ctx, 1, metric.WithAttributes(
		attribute.Int("risk_score", riskScore),
	))
}

func RecordOrderBackordered(ctx context.Context) {
	ensureMetrics()
	ordersBackordered.Add(ctx, 1)
}

func RecordOrderPaymentFailed(ctx context.Context, reason string) {
	ensureMetrics()
	ordersPaymentFailed.Add(ctx, 1, metric.WithAttributes(
		attribute.String("reason", reason),
	))
}

func RecordOrderProcessingDuration(ctx context.Context, durationSeconds float64, decisionPath string) {
	ensureMetrics()
	orderProcessingDuration.Record(ctx, durationSeconds, metric.WithAttributes(
		attribute.String("decision_path", decisionPath),
	))
}

func RecordFraudRiskScore(ctx context.Context, score int, customerTier string) {
	ensureMetrics()
	fraudRiskScore.Record(ctx, int64(score), metric.WithAttributes(
		attribute.String("customer_tier", customerTier),
	))
}
