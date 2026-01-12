package workflows

import (
	"time"

	"go.temporal.io/sdk/temporal"
	"go.temporal.io/sdk/workflow"

	"github.com/base-14/examples/go/go-temporal-postgres/internal/activities"
)

type OrderInput struct {
	OrderID      string           `json:"order_id"`
	CustomerID   string           `json:"customer_id"`
	CustomerTier string           `json:"customer_tier"`
	TotalAmount  float64          `json:"total_amount"`
	Items        []OrderItemInput `json:"items"`
}

type OrderItemInput struct {
	ProductID string  `json:"product_id"`
	Quantity  int     `json:"quantity"`
	Price     float64 `json:"price"`
}

type OrderResult struct {
	OrderID      string `json:"order_id"`
	Status       string `json:"status"`
	DecisionPath string `json:"decision_path"`
	RiskScore    int    `json:"risk_score,omitempty"`
	Message      string `json:"message,omitempty"`
}

const (
	FraudAssessmentQueue = "fraud-assessment-queue"
	InventoryQueue       = "inventory-queue"
	PaymentQueue         = "payment-queue"
	ShippingQueue        = "shipping-queue"
	NotificationQueue    = "notification-queue"
)

func OrderFulfillmentWorkflow(ctx workflow.Context, input OrderInput) (*OrderResult, error) {
	logger := workflow.GetLogger(ctx)
	logger.Info("Starting order fulfillment workflow", "order_id", input.OrderID)

	startTime := workflow.Now(ctx)

	defaultRetryPolicy := &temporal.RetryPolicy{
		InitialInterval:    time.Second,
		BackoffCoefficient: 2.0,
		MaximumInterval:    time.Minute,
		MaximumAttempts:    3,
	}

	ao := workflow.ActivityOptions{
		StartToCloseTimeout: time.Minute,
		RetryPolicy:         defaultRetryPolicy,
	}
	ctx = workflow.WithActivityOptions(ctx, ao)

	fraudAO := workflow.ActivityOptions{
		TaskQueue:           FraudAssessmentQueue,
		StartToCloseTimeout: time.Minute,
		RetryPolicy:         defaultRetryPolicy,
	}
	fraudCtx := workflow.WithActivityOptions(ctx, fraudAO)

	inventoryAO := workflow.ActivityOptions{
		TaskQueue:           InventoryQueue,
		StartToCloseTimeout: time.Minute,
		RetryPolicy:         defaultRetryPolicy,
	}
	inventoryCtx := workflow.WithActivityOptions(ctx, inventoryAO)

	paymentAO := workflow.ActivityOptions{
		TaskQueue:           PaymentQueue,
		StartToCloseTimeout: time.Minute,
		RetryPolicy:         defaultRetryPolicy,
	}
	paymentCtx := workflow.WithActivityOptions(ctx, paymentAO)

	shippingAO := workflow.ActivityOptions{
		TaskQueue:           ShippingQueue,
		StartToCloseTimeout: time.Minute,
		RetryPolicy:         defaultRetryPolicy,
	}
	shippingCtx := workflow.WithActivityOptions(ctx, shippingAO)

	notificationAO := workflow.ActivityOptions{
		TaskQueue:           NotificationQueue,
		StartToCloseTimeout: time.Minute,
		RetryPolicy:         defaultRetryPolicy,
	}
	notificationCtx := workflow.WithActivityOptions(ctx, notificationAO)

	recordMetrics := func(result *OrderResult, riskScore int, failureReason string) {
		duration := workflow.Now(ctx).Sub(startTime).Seconds()
		_ = workflow.ExecuteActivity(ctx, activities.RecordOrderMetrics, activities.RecordMetricsInput{
			OrderID:       input.OrderID,
			CustomerTier:  input.CustomerTier,
			DecisionPath:  result.DecisionPath,
			RiskScore:     riskScore,
			DurationSecs:  duration,
			FailureReason: failureReason,
		}).Get(ctx, nil)
	}

	var validateResult activities.ValidateOrderResult
	if err := workflow.ExecuteActivity(ctx, activities.ValidateOrder, activities.ValidateOrderInput{
		OrderID:     input.OrderID,
		CustomerID:  input.CustomerID,
		TotalAmount: input.TotalAmount,
		Items:       toActivityItems(input.Items),
	}).Get(ctx, &validateResult); err != nil {
		result := &OrderResult{
			OrderID:      input.OrderID,
			Status:       "validation_failed",
			DecisionPath: "validation_error",
			Message:      err.Error(),
		}
		recordMetrics(result, 0, err.Error())
		return result, nil
	}

	if !validateResult.Valid {
		result := &OrderResult{
			OrderID:      input.OrderID,
			Status:       "invalid",
			DecisionPath: "validation_failed",
			Message:      validateResult.Reason,
		}
		recordMetrics(result, 0, validateResult.Reason)
		return result, nil
	}

	var fraudResult activities.FraudAssessmentResult
	if err := workflow.ExecuteActivity(fraudCtx, "FraudAssessment", activities.FraudAssessmentInput{
		OrderID:      input.OrderID,
		CustomerID:   input.CustomerID,
		CustomerTier: input.CustomerTier,
		TotalAmount:  input.TotalAmount,
	}).Get(ctx, &fraudResult); err != nil {
		result := &OrderResult{
			OrderID:      input.OrderID,
			Status:       "fraud_check_failed",
			DecisionPath: "fraud_error",
			Message:      err.Error(),
		}
		recordMetrics(result, 0, err.Error())
		return result, nil
	}

	if fraudResult.RiskScore > 80 {
		logger.Info("High risk order, requiring manual review", "risk_score", fraudResult.RiskScore)
		return handleManualReview(ctx, input, fraudResult.RiskScore, startTime)
	}

	var inventoryResult activities.InventoryCheckResult
	if err := workflow.ExecuteActivity(inventoryCtx, "InventoryCheck", activities.InventoryCheckInput{
		OrderID: input.OrderID,
		Items:   toActivityItems(input.Items),
	}).Get(ctx, &inventoryResult); err != nil {
		result := &OrderResult{
			OrderID:      input.OrderID,
			Status:       "inventory_check_failed",
			DecisionPath: "inventory_error",
			Message:      err.Error(),
		}
		recordMetrics(result, fraudResult.RiskScore, err.Error())
		return result, nil
	}

	if !inventoryResult.AllAvailable {
		logger.Info("Items not available, creating backorder")
		return handleBackorder(ctx, input, inventoryResult, fraudResult.RiskScore, startTime)
	}

	var paymentResult activities.PaymentResult
	if err := workflow.ExecuteActivity(paymentCtx, "ProcessPayment", activities.PaymentInput{
		OrderID:    input.OrderID,
		CustomerID: input.CustomerID,
		Amount:     input.TotalAmount,
	}).Get(ctx, &paymentResult); err != nil {
		result := &OrderResult{
			OrderID:      input.OrderID,
			Status:       "payment_failed",
			DecisionPath: "payment_error",
			Message:      err.Error(),
		}
		recordMetrics(result, fraudResult.RiskScore, err.Error())
		return result, nil
	}

	if !paymentResult.Success {
		logger.Info("Payment failed", "reason", paymentResult.Reason)
		result := &OrderResult{
			OrderID:      input.OrderID,
			Status:       "payment_failed",
			DecisionPath: "payment_declined",
			Message:      paymentResult.Reason,
		}
		recordMetrics(result, fraudResult.RiskScore, paymentResult.Reason)
		return result, nil
	}

	var shippingResult activities.ShippingResult
	if err := workflow.ExecuteActivity(shippingCtx, "ReserveShipping", activities.ShippingInput{
		OrderID:    input.OrderID,
		CustomerID: input.CustomerID,
		Items:      toActivityItems(input.Items),
	}).Get(ctx, &shippingResult); err != nil {
		logger.Warn("Shipping reservation failed, but continuing", "error", err)
	}

	_ = workflow.ExecuteActivity(notificationCtx, "SendConfirmation", activities.NotificationInput{
		OrderID:    input.OrderID,
		CustomerID: input.CustomerID,
		Type:       "order_confirmed",
		Message:    "Your order has been confirmed and is being processed.",
	}).Get(ctx, nil)

	logger.Info("Order fulfillment completed successfully", "order_id", input.OrderID)
	result := &OrderResult{
		OrderID:      input.OrderID,
		Status:       "completed",
		DecisionPath: "auto_approved",
		RiskScore:    fraudResult.RiskScore,
		Message:      "Order processed successfully",
	}
	recordMetrics(result, fraudResult.RiskScore, "")
	return result, nil
}

func handleManualReview(ctx workflow.Context, input OrderInput, riskScore int, startTime time.Time) (*OrderResult, error) {
	logger := workflow.GetLogger(ctx)

	notifyCtx := workflow.WithActivityOptions(ctx, workflow.ActivityOptions{
		TaskQueue:           NotificationQueue,
		StartToCloseTimeout: time.Minute,
	})
	_ = workflow.ExecuteActivity(notifyCtx, "SendConfirmation", activities.NotificationInput{
		OrderID:    input.OrderID,
		CustomerID: input.CustomerID,
		Type:       "manual_review",
		Message:    "Your order is under review.",
	}).Get(ctx, nil)

	duration := workflow.Now(ctx).Sub(startTime).Seconds()
	_ = workflow.ExecuteActivity(ctx, activities.RecordOrderMetrics, activities.RecordMetricsInput{
		OrderID:      input.OrderID,
		CustomerTier: input.CustomerTier,
		DecisionPath: "manual_review",
		RiskScore:    riskScore,
		DurationSecs: duration,
	}).Get(ctx, nil)

	reviewChannel := workflow.GetSignalChannel(ctx, "manual-review-decision")
	reviewTimeout := workflow.NewTimer(ctx, 24*time.Hour)

	var decision string
	selector := workflow.NewSelector(ctx)

	selector.AddReceive(reviewChannel, func(c workflow.ReceiveChannel, more bool) {
		c.Receive(ctx, &decision)
	})

	selector.AddFuture(reviewTimeout, func(f workflow.Future) {
		decision = "timeout"
	})

	selector.Select(ctx)

	finalDuration := workflow.Now(ctx).Sub(startTime).Seconds()

	if decision == "approved" {
		logger.Info("Manual review approved", "order_id", input.OrderID)
		result := &OrderResult{
			OrderID:      input.OrderID,
			Status:       "approved",
			DecisionPath: "manual_approved",
			RiskScore:    riskScore,
			Message:      "Order approved after manual review",
		}
		_ = workflow.ExecuteActivity(ctx, activities.RecordOrderMetrics, activities.RecordMetricsInput{
			OrderID:      input.OrderID,
			CustomerTier: input.CustomerTier,
			DecisionPath: result.DecisionPath,
			RiskScore:    riskScore,
			DurationSecs: finalDuration,
		}).Get(ctx, nil)
		return result, nil
	}

	logger.Info("Manual review rejected or timed out", "order_id", input.OrderID, "decision", decision)
	result := &OrderResult{
		OrderID:      input.OrderID,
		Status:       "rejected",
		DecisionPath: "manual_rejected",
		RiskScore:    riskScore,
		Message:      "Order rejected during manual review",
	}
	_ = workflow.ExecuteActivity(ctx, activities.RecordOrderMetrics, activities.RecordMetricsInput{
		OrderID:       input.OrderID,
		CustomerTier:  input.CustomerTier,
		DecisionPath:  result.DecisionPath,
		RiskScore:     riskScore,
		DurationSecs:  finalDuration,
		FailureReason: "manual_review_" + decision,
	}).Get(ctx, nil)
	return result, nil
}

func handleBackorder(ctx workflow.Context, input OrderInput, inventoryResult activities.InventoryCheckResult, riskScore int, startTime time.Time) (*OrderResult, error) {
	notifyCtx := workflow.WithActivityOptions(ctx, workflow.ActivityOptions{
		TaskQueue:           NotificationQueue,
		StartToCloseTimeout: time.Minute,
	})
	_ = workflow.ExecuteActivity(notifyCtx, "SendConfirmation", activities.NotificationInput{
		OrderID:    input.OrderID,
		CustomerID: input.CustomerID,
		Type:       "backorder",
		Message:    "Some items in your order are currently out of stock. We'll notify you when they become available.",
	}).Get(ctx, nil)

	duration := workflow.Now(ctx).Sub(startTime).Seconds()
	result := &OrderResult{
		OrderID:      input.OrderID,
		Status:       "backordered",
		DecisionPath: "backorder",
		Message:      "Order placed on backorder due to insufficient stock",
	}
	_ = workflow.ExecuteActivity(ctx, activities.RecordOrderMetrics, activities.RecordMetricsInput{
		OrderID:      input.OrderID,
		CustomerTier: input.CustomerTier,
		DecisionPath: result.DecisionPath,
		RiskScore:    riskScore,
		DurationSecs: duration,
	}).Get(ctx, nil)
	return result, nil
}

func toActivityItems(items []OrderItemInput) []activities.OrderItem {
	result := make([]activities.OrderItem, len(items))
	for i, item := range items {
		result[i] = activities.OrderItem{
			ProductID: item.ProductID,
			Quantity:  item.Quantity,
			Price:     item.Price,
		}
	}
	return result
}
