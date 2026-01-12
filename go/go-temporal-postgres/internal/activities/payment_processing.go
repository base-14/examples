package activities

import (
	"context"
	"fmt"
	"log/slog"

	"github.com/google/uuid"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/codes"
	"go.opentelemetry.io/otel/metric"
	"go.opentelemetry.io/otel/trace"
	"go.temporal.io/sdk/activity"
)

var (
	paymentMeter         = otel.Meter("payment-processing")
	paymentAttemptsCount metric.Int64Counter
	paymentFailuresCount metric.Int64Counter
	paymentSuccessCount  metric.Int64Counter
	paymentAmountTotal   metric.Float64Counter
	paymentLatency       metric.Float64Histogram
)

func init() {
	var err error

	paymentAttemptsCount, err = paymentMeter.Int64Counter("payment.attempts",
		metric.WithDescription("Total payment attempts"),
		metric.WithUnit("{attempt}"),
	)
	if err != nil {
		panic(err)
	}

	paymentFailuresCount, err = paymentMeter.Int64Counter("payment.failures",
		metric.WithDescription("Payment failures"),
		metric.WithUnit("{failure}"),
	)
	if err != nil {
		panic(err)
	}

	paymentSuccessCount, err = paymentMeter.Int64Counter("payment.successes",
		metric.WithDescription("Successful payments"),
		metric.WithUnit("{success}"),
	)
	if err != nil {
		panic(err)
	}

	paymentAmountTotal, err = paymentMeter.Float64Counter("payment.amount.total",
		metric.WithDescription("Total payment amount processed"),
		metric.WithUnit("{USD}"),
	)
	if err != nil {
		panic(err)
	}

	paymentLatency, err = paymentMeter.Float64Histogram("payment.latency",
		metric.WithDescription("Payment processing latency"),
		metric.WithUnit("ms"),
		metric.WithExplicitBucketBoundaries(1, 5, 10, 25, 50, 100, 250, 500, 1000),
	)
	if err != nil {
		panic(err)
	}
}

func ProcessPayment(ctx context.Context, input PaymentInput) (*PaymentResult, error) {
	activityInfo := activity.GetInfo(ctx)
	startTime := activity.GetInfo(ctx).StartedTime

	ctx, span := otel.Tracer("activities").Start(ctx, "process_payment",
		trace.WithAttributes(
			attribute.String("order.id", input.OrderID),
			attribute.String("customer.id", input.CustomerID),
			attribute.Float64("payment.amount", input.Amount),
			attribute.String("temporal.activity_id", activityInfo.ActivityID),
			attribute.String("temporal.workflow_id", activityInfo.WorkflowExecution.ID),
		),
	)
	defer span.End()

	traceID := span.SpanContext().TraceID().String()
	spanID := span.SpanContext().SpanID().String()

	// NOTE: Using order_id, workflow_id, and trace_id as metric attributes creates
	// high-cardinality metrics. In production, avoid these - use low-cardinality
	// attributes like status, payment_method, etc. These IDs belong in traces/logs.
	commonAttrs := metric.WithAttributes(
		attribute.String("order_id", input.OrderID),
		attribute.String("workflow_id", activityInfo.WorkflowExecution.ID),
		attribute.String("trace_id", traceID),
	)

	paymentAttemptsCount.Add(ctx, 1, commonAttrs)

	if input.CustomerID == "test_decline" {
		span.SetStatus(codes.Error, "payment declined")
		span.SetAttributes(
			attribute.Bool("payment.success", false),
			attribute.String("payment.decline_reason", "test_decline"),
		)
		span.RecordError(fmt.Errorf("payment declined: test decline scenario"))

		paymentFailuresCount.Add(ctx, 1,
			metric.WithAttributes(
				attribute.String("order_id", input.OrderID),
				attribute.String("workflow_id", activityInfo.WorkflowExecution.ID),
				attribute.String("trace_id", traceID),
				attribute.String("decline_reason", "test_decline"),
				attribute.Float64("amount", input.Amount),
			),
		)

		latencyMs := float64(activity.GetInfo(ctx).StartedTime.Sub(startTime).Milliseconds())
		paymentLatency.Record(ctx, latencyMs,
			metric.WithAttributes(
				attribute.String("status", "failed"),
				attribute.String("trace_id", traceID),
			),
		)

		slog.ErrorContext(ctx, "payment declined",
			slog.String("order_id", input.OrderID),
			slog.String("customer_id", input.CustomerID),
			slog.Float64("amount", input.Amount),
			slog.String("decline_reason", "test_decline"),
			slog.String("workflow_id", activityInfo.WorkflowExecution.ID),
			slog.String("trace_id", traceID),
			slog.String("span_id", spanID),
		)

		return &PaymentResult{
			Success: false,
			Reason:  "Payment declined: test decline scenario",
		}, nil
	}

	transactionID := fmt.Sprintf("txn-%s", uuid.New().String()[:8])

	span.SetStatus(codes.Ok, "payment successful")
	span.SetAttributes(
		attribute.Bool("payment.success", true),
		attribute.String("payment.transaction_id", transactionID),
	)

	paymentSuccessCount.Add(ctx, 1, commonAttrs)
	paymentAmountTotal.Add(ctx, input.Amount, commonAttrs)

	latencyMs := float64(activity.GetInfo(ctx).StartedTime.Sub(startTime).Milliseconds())
	paymentLatency.Record(ctx, latencyMs,
		metric.WithAttributes(
			attribute.String("status", "success"),
			attribute.String("trace_id", traceID),
		),
	)

	slog.InfoContext(ctx, "payment processed successfully",
		slog.String("order_id", input.OrderID),
		slog.String("customer_id", input.CustomerID),
		slog.Float64("amount", input.Amount),
		slog.String("transaction_id", transactionID),
		slog.String("workflow_id", activityInfo.WorkflowExecution.ID),
		slog.String("trace_id", traceID),
		slog.String("span_id", spanID),
	)

	return &PaymentResult{
		Success:       true,
		TransactionID: transactionID,
	}, nil
}
