package handlers

import (
	"errors"
	"fmt"
	"net/http"

	"github.com/google/uuid"
	"github.com/labstack/echo/v4"
	"go.temporal.io/sdk/client"
	"gorm.io/gorm"

	"github.com/base-14/examples/go/go-temporal-postgres/internal/models"
	"github.com/base-14/examples/go/go-temporal-postgres/internal/workflows"
)

type OrderHandler struct {
	db             *gorm.DB
	temporalClient client.Client
	taskQueue      string
}

func NewOrderHandler(db *gorm.DB, temporalClient client.Client, taskQueue string) *OrderHandler {
	return &OrderHandler{
		db:             db,
		temporalClient: temporalClient,
		taskQueue:      taskQueue,
	}
}

type CreateOrderRequest struct {
	CustomerID    string            `json:"customer_id"`
	CustomerTier  string            `json:"customer_tier"`
	Items         []CreateOrderItem `json:"items"`
	PaymentMethod string            `json:"payment_method,omitempty"`
}

type CreateOrderItem struct {
	ProductID string  `json:"product_id"`
	Quantity  int     `json:"quantity"`
	Price     float64 `json:"price,omitempty"`
}

func (h *OrderHandler) Create(c echo.Context) error {
	var req CreateOrderRequest
	if err := c.Bind(&req); err != nil {
		return echo.NewHTTPError(http.StatusBadRequest, "invalid request body")
	}

	if req.CustomerID == "" {
		return echo.NewHTTPError(http.StatusBadRequest, "customer_id is required")
	}
	if len(req.Items) == 0 {
		return echo.NewHTTPError(http.StatusBadRequest, "at least one item is required")
	}

	var totalAmount float64
	orderItems := make([]models.OrderItem, 0, len(req.Items))
	workflowItems := make([]workflows.OrderItemInput, 0, len(req.Items))
	for _, item := range req.Items {
		price := item.Price
		if price == 0 {
			var product models.Product
			if err := h.db.WithContext(c.Request().Context()).Where("sku = ?", item.ProductID).First(&product).Error; err == nil {
				price = product.Price
			} else {
				price = 10.00
			}
		}
		totalAmount += price * float64(item.Quantity)
		orderItems = append(orderItems, models.OrderItem{
			ProductID: item.ProductID,
			Quantity:  item.Quantity,
			Price:     price,
		})
		workflowItems = append(workflowItems, workflows.OrderItemInput{
			ProductID: item.ProductID,
			Quantity:  item.Quantity,
			Price:     price,
		})
	}

	customerID := req.CustomerID
	if req.PaymentMethod == "test_decline" {
		customerID = "test_decline"
	}

	order := models.Order{
		CustomerID:   req.CustomerID,
		CustomerTier: req.CustomerTier,
		Status:       models.OrderStatusPending,
		TotalAmount:  totalAmount,
		Items:        orderItems,
	}

	if order.CustomerTier == "" {
		order.CustomerTier = "standard"
	}

	if err := h.db.WithContext(c.Request().Context()).Create(&order).Error; err != nil {
		return echo.NewHTTPError(http.StatusInternalServerError, "failed to create order")
	}

	workflowID := fmt.Sprintf("order-%s", order.ID.String())
	workflowInput := workflows.OrderInput{
		OrderID:      order.ID.String(),
		CustomerID:   customerID,
		CustomerTier: order.CustomerTier,
		TotalAmount:  totalAmount,
		Items:        workflowItems,
	}

	workflowOptions := client.StartWorkflowOptions{
		ID:        workflowID,
		TaskQueue: h.taskQueue,
	}

	_, err := h.temporalClient.ExecuteWorkflow(c.Request().Context(), workflowOptions, workflows.OrderFulfillmentWorkflow, workflowInput)
	if err != nil {
		order.Status = models.OrderStatusCancelled
		h.db.WithContext(c.Request().Context()).Save(&order)
		return echo.NewHTTPError(http.StatusInternalServerError, "failed to start workflow: "+err.Error())
	}

	order.WorkflowID = workflowID
	order.Status = models.OrderStatusProcessing
	h.db.WithContext(c.Request().Context()).Save(&order)

	return c.JSON(http.StatusCreated, map[string]interface{}{
		"order":       order,
		"workflow_id": workflowID,
	})
}

func (h *OrderHandler) List(c echo.Context) error {
	var orders []models.Order
	if err := h.db.WithContext(c.Request().Context()).Preload("Items").Find(&orders).Error; err != nil {
		return echo.NewHTTPError(http.StatusInternalServerError, "failed to fetch orders")
	}
	return c.JSON(http.StatusOK, map[string]interface{}{
		"orders": orders,
	})
}

func (h *OrderHandler) Get(c echo.Context) error {
	id := c.Param("id")
	parsedID, err := uuid.Parse(id)
	if err != nil {
		return echo.NewHTTPError(http.StatusBadRequest, "invalid order id")
	}

	var order models.Order
	if err := h.db.WithContext(c.Request().Context()).Preload("Items").Where("id = ?", parsedID).First(&order).Error; err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return echo.NewHTTPError(http.StatusNotFound, "order not found")
		}
		return echo.NewHTTPError(http.StatusInternalServerError, "failed to fetch order")
	}
	return c.JSON(http.StatusOK, map[string]interface{}{
		"order": order,
	})
}
