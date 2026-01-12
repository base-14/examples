package tests

import (
	"context"
	"testing"

	"github.com/stretchr/testify/require"
	"go.temporal.io/sdk/testsuite"

	"github.com/base-14/examples/go/go-temporal-postgres/internal/activities"
)

func TestValidateOrder_Valid(t *testing.T) {
	input := activities.ValidateOrderInput{
		OrderID:     "test-order",
		CustomerID:  "test-customer",
		TotalAmount: 100.00,
		Items: []activities.OrderItem{
			{ProductID: "prod-1", Quantity: 2, Price: 50.00},
		},
	}

	result, err := activities.ValidateOrder(context.Background(), input)
	require.NoError(t, err)
	require.True(t, result.Valid)
}

func TestValidateOrder_MissingCustomerID(t *testing.T) {
	input := activities.ValidateOrderInput{
		OrderID:     "test-order",
		CustomerID:  "",
		TotalAmount: 100.00,
		Items: []activities.OrderItem{
			{ProductID: "prod-1", Quantity: 1, Price: 100.00},
		},
	}

	result, err := activities.ValidateOrder(context.Background(), input)
	require.NoError(t, err)
	require.False(t, result.Valid)
	require.Contains(t, result.Reason, "customer ID")
}

func TestValidateOrder_NoItems(t *testing.T) {
	input := activities.ValidateOrderInput{
		OrderID:     "test-order",
		CustomerID:  "test-customer",
		TotalAmount: 100.00,
		Items:       []activities.OrderItem{},
	}

	result, err := activities.ValidateOrder(context.Background(), input)
	require.NoError(t, err)
	require.False(t, result.Valid)
	require.Contains(t, result.Reason, "at least one item")
}

func TestFraudAssessment_LowRisk(t *testing.T) {
	input := activities.FraudAssessmentInput{
		OrderID:      "test-order",
		CustomerID:   "premium-customer",
		CustomerTier: "premium",
		TotalAmount:  50.00,
	}

	result, err := activities.FraudAssessment(context.Background(), input)
	require.NoError(t, err)
	require.LessOrEqual(t, result.RiskScore, 80)
}

func TestFraudAssessment_HighRisk(t *testing.T) {
	input := activities.FraudAssessmentInput{
		OrderID:      "test-order",
		CustomerID:   "new-customer",
		CustomerTier: "new",
		TotalAmount:  6000.00,
	}

	result, err := activities.FraudAssessment(context.Background(), input)
	require.NoError(t, err)
	require.Greater(t, result.RiskScore, 80)
}

func TestInventoryCheck_AllAvailable(t *testing.T) {
	input := activities.InventoryCheckInput{
		OrderID: "test-order",
		Items: []activities.OrderItem{
			{ProductID: "prod-1", Quantity: 5, Price: 29.99},
		},
	}

	result, err := activities.InventoryCheck(context.Background(), input)
	require.NoError(t, err)
	require.True(t, result.AllAvailable)
}

func TestInventoryCheck_OutOfStock(t *testing.T) {
	input := activities.InventoryCheckInput{
		OrderID: "test-order",
		Items: []activities.OrderItem{
			{ProductID: "out-of-stock-item", Quantity: 10, Price: 199.99},
		},
	}

	result, err := activities.InventoryCheck(context.Background(), input)
	require.NoError(t, err)
	require.False(t, result.AllAvailable)
	require.Len(t, result.UnavailableItems, 1)
}

func TestProcessPayment_Success(t *testing.T) {
	testSuite := &testsuite.WorkflowTestSuite{}
	env := testSuite.NewTestActivityEnvironment()
	env.RegisterActivity(activities.ProcessPayment)

	input := activities.PaymentInput{
		OrderID:    "test-order",
		CustomerID: "test-customer",
		Amount:     100.00,
	}

	val, err := env.ExecuteActivity(activities.ProcessPayment, input)
	require.NoError(t, err)

	var result activities.PaymentResult
	require.NoError(t, val.Get(&result))
	require.True(t, result.Success)
	require.NotEmpty(t, result.TransactionID)
}

func TestProcessPayment_Decline(t *testing.T) {
	testSuite := &testsuite.WorkflowTestSuite{}
	env := testSuite.NewTestActivityEnvironment()
	env.RegisterActivity(activities.ProcessPayment)

	input := activities.PaymentInput{
		OrderID:    "test-order",
		CustomerID: "test_decline",
		Amount:     100.00,
	}

	val, err := env.ExecuteActivity(activities.ProcessPayment, input)
	require.NoError(t, err)

	var result activities.PaymentResult
	require.NoError(t, val.Get(&result))
	require.False(t, result.Success)
	require.Contains(t, result.Reason, "declined")
}

func TestReserveShipping(t *testing.T) {
	input := activities.ShippingInput{
		OrderID:    "test-order",
		CustomerID: "test-customer",
		Items: []activities.OrderItem{
			{ProductID: "prod-1", Quantity: 1, Price: 29.99},
		},
	}

	result, err := activities.ReserveShipping(context.Background(), input)
	require.NoError(t, err)
	require.True(t, result.Reserved)
	require.NotEmpty(t, result.TrackingID)
}

func TestSendConfirmation(t *testing.T) {
	input := activities.NotificationInput{
		OrderID:    "test-order",
		CustomerID: "test-customer",
		Type:       "order_confirmed",
		Message:    "Your order has been confirmed.",
	}

	err := activities.SendConfirmation(context.Background(), input)
	require.NoError(t, err)
}
