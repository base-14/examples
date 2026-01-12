package tests

import (
	"testing"

	"github.com/stretchr/testify/mock"
	"github.com/stretchr/testify/require"
	"go.temporal.io/sdk/testsuite"

	"github.com/base-14/examples/go/go-temporal-postgres/internal/activities"
	"github.com/base-14/examples/go/go-temporal-postgres/internal/workflows"
)

func TestOrderFulfillmentWorkflow_AutoApprove(t *testing.T) {
	testSuite := &testsuite.WorkflowTestSuite{}
	env := testSuite.NewTestWorkflowEnvironment()

	env.OnActivity(activities.ValidateOrder, mock.Anything, mock.Anything).Return(&activities.ValidateOrderResult{
		Valid: true,
	}, nil)

	env.OnActivity(activities.FraudAssessment, mock.Anything, mock.Anything).Return(&activities.FraudAssessmentResult{
		RiskScore: 20,
	}, nil)

	env.OnActivity(activities.InventoryCheck, mock.Anything, mock.Anything).Return(&activities.InventoryCheckResult{
		AllAvailable: true,
	}, nil)

	env.OnActivity(activities.ProcessPayment, mock.Anything, mock.Anything).Return(&activities.PaymentResult{
		Success:       true,
		TransactionID: "txn-123",
	}, nil)

	env.OnActivity(activities.ReserveShipping, mock.Anything, mock.Anything).Return(&activities.ShippingResult{
		Reserved:   true,
		TrackingID: "TRK-123",
	}, nil)

	env.OnActivity(activities.SendConfirmation, mock.Anything, mock.Anything).Return(nil)
	env.OnActivity(activities.RecordOrderMetrics, mock.Anything, mock.Anything).Return(nil)

	input := workflows.OrderInput{
		OrderID:      "test-order-1",
		CustomerID:   "premium-customer",
		CustomerTier: "premium",
		TotalAmount:  50.00,
		Items: []workflows.OrderItemInput{
			{ProductID: "prod-1", Quantity: 1, Price: 50.00},
		},
	}

	env.ExecuteWorkflow(workflows.OrderFulfillmentWorkflow, input)

	require.True(t, env.IsWorkflowCompleted())
	require.NoError(t, env.GetWorkflowError())

	var result workflows.OrderResult
	require.NoError(t, env.GetWorkflowResult(&result))
	require.Equal(t, "completed", result.Status)
	require.Equal(t, "auto_approved", result.DecisionPath)
}

func TestOrderFulfillmentWorkflow_ManualReview(t *testing.T) {
	testSuite := &testsuite.WorkflowTestSuite{}
	env := testSuite.NewTestWorkflowEnvironment()

	env.OnActivity(activities.ValidateOrder, mock.Anything, mock.Anything).Return(&activities.ValidateOrderResult{
		Valid: true,
	}, nil)

	env.OnActivity(activities.FraudAssessment, mock.Anything, mock.Anything).Return(&activities.FraudAssessmentResult{
		RiskScore: 85,
	}, nil)

	env.OnActivity(activities.SendConfirmation, mock.Anything, mock.Anything).Return(nil)
	env.OnActivity(activities.RecordOrderMetrics, mock.Anything, mock.Anything).Return(nil)

	env.RegisterDelayedCallback(func() {
		env.SignalWorkflow("manual-review-decision", "approved")
	}, 0)

	input := workflows.OrderInput{
		OrderID:      "test-order-2",
		CustomerID:   "new-customer",
		CustomerTier: "new",
		TotalAmount:  5000.00,
		Items: []workflows.OrderItemInput{
			{ProductID: "prod-1", Quantity: 100, Price: 50.00},
		},
	}

	env.ExecuteWorkflow(workflows.OrderFulfillmentWorkflow, input)

	require.True(t, env.IsWorkflowCompleted())
	require.NoError(t, env.GetWorkflowError())

	var result workflows.OrderResult
	require.NoError(t, env.GetWorkflowResult(&result))
	require.Equal(t, "approved", result.Status)
	require.Equal(t, "manual_approved", result.DecisionPath)
}

func TestOrderFulfillmentWorkflow_Backorder(t *testing.T) {
	testSuite := &testsuite.WorkflowTestSuite{}
	env := testSuite.NewTestWorkflowEnvironment()

	env.OnActivity(activities.ValidateOrder, mock.Anything, mock.Anything).Return(&activities.ValidateOrderResult{
		Valid: true,
	}, nil)

	env.OnActivity(activities.FraudAssessment, mock.Anything, mock.Anything).Return(&activities.FraudAssessmentResult{
		RiskScore: 20,
	}, nil)

	env.OnActivity(activities.InventoryCheck, mock.Anything, mock.Anything).Return(&activities.InventoryCheckResult{
		AllAvailable: false,
		UnavailableItems: []activities.UnavailableItem{
			{ProductID: "out-of-stock-item", Requested: 100, Available: 0},
		},
	}, nil)

	env.OnActivity(activities.SendConfirmation, mock.Anything, mock.Anything).Return(nil)
	env.OnActivity(activities.RecordOrderMetrics, mock.Anything, mock.Anything).Return(nil)

	input := workflows.OrderInput{
		OrderID:      "test-order-3",
		CustomerID:   "test-customer",
		CustomerTier: "standard",
		TotalAmount:  100.00,
		Items: []workflows.OrderItemInput{
			{ProductID: "out-of-stock-item", Quantity: 100, Price: 1.00},
		},
	}

	env.ExecuteWorkflow(workflows.OrderFulfillmentWorkflow, input)

	require.True(t, env.IsWorkflowCompleted())
	require.NoError(t, env.GetWorkflowError())

	var result workflows.OrderResult
	require.NoError(t, env.GetWorkflowResult(&result))
	require.Equal(t, "backordered", result.Status)
	require.Equal(t, "backorder", result.DecisionPath)
}

func TestOrderFulfillmentWorkflow_PaymentFailed(t *testing.T) {
	testSuite := &testsuite.WorkflowTestSuite{}
	env := testSuite.NewTestWorkflowEnvironment()

	env.OnActivity(activities.ValidateOrder, mock.Anything, mock.Anything).Return(&activities.ValidateOrderResult{
		Valid: true,
	}, nil)

	env.OnActivity(activities.FraudAssessment, mock.Anything, mock.Anything).Return(&activities.FraudAssessmentResult{
		RiskScore: 20,
	}, nil)

	env.OnActivity(activities.InventoryCheck, mock.Anything, mock.Anything).Return(&activities.InventoryCheckResult{
		AllAvailable: true,
	}, nil)

	env.OnActivity(activities.ProcessPayment, mock.Anything, mock.Anything).Return(&activities.PaymentResult{
		Success: false,
		Reason:  "Card declined",
	}, nil)

	env.OnActivity(activities.RecordOrderMetrics, mock.Anything, mock.Anything).Return(nil)

	input := workflows.OrderInput{
		OrderID:      "test-order-4",
		CustomerID:   "test-customer",
		CustomerTier: "standard",
		TotalAmount:  100.00,
		Items: []workflows.OrderItemInput{
			{ProductID: "prod-1", Quantity: 1, Price: 100.00},
		},
	}

	env.ExecuteWorkflow(workflows.OrderFulfillmentWorkflow, input)

	require.True(t, env.IsWorkflowCompleted())
	require.NoError(t, env.GetWorkflowError())

	var result workflows.OrderResult
	require.NoError(t, env.GetWorkflowResult(&result))
	require.Equal(t, "payment_failed", result.Status)
	require.Equal(t, "payment_declined", result.DecisionPath)
}
