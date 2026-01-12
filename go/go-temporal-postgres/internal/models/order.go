package models

import (
	"time"

	"github.com/google/uuid"
	"gorm.io/gorm"
)

type OrderStatus string

const (
	OrderStatusPending       OrderStatus = "pending"
	OrderStatusProcessing    OrderStatus = "processing"
	OrderStatusApproved      OrderStatus = "approved"
	OrderStatusManualReview  OrderStatus = "manual_review"
	OrderStatusBackordered   OrderStatus = "backordered"
	OrderStatusPaymentFailed OrderStatus = "payment_failed"
	OrderStatusCompleted     OrderStatus = "completed"
	OrderStatusCancelled     OrderStatus = "cancelled"
)

type Order struct {
	ID           uuid.UUID   `gorm:"type:uuid;primaryKey" json:"id"`
	CustomerID   string      `gorm:"not null;index" json:"customer_id"`
	CustomerTier string      `gorm:"default:'standard'" json:"customer_tier"`
	Status       OrderStatus `gorm:"type:varchar(50);default:'pending';index" json:"status"`
	TotalAmount  float64     `gorm:"not null" json:"total_amount"`
	RiskScore    int         `gorm:"default:0" json:"risk_score"`
	DecisionPath string      `gorm:"type:varchar(50)" json:"decision_path,omitempty"`
	WorkflowID   string      `gorm:"index" json:"workflow_id,omitempty"`
	Items        []OrderItem `gorm:"foreignKey:OrderID" json:"items"`
	CreatedAt    time.Time   `json:"created_at"`
	UpdatedAt    time.Time   `json:"updated_at"`
}

func (o *Order) BeforeCreate(tx *gorm.DB) error {
	if o.ID == uuid.Nil {
		o.ID = uuid.New()
	}
	return nil
}

type OrderItem struct {
	ID        uuid.UUID `gorm:"type:uuid;primaryKey" json:"id"`
	OrderID   uuid.UUID `gorm:"type:uuid;not null;index" json:"order_id"`
	ProductID string    `gorm:"not null" json:"product_id"`
	Quantity  int       `gorm:"not null" json:"quantity"`
	Price     float64   `gorm:"not null" json:"price"`
	CreatedAt time.Time `json:"created_at"`
}

func (oi *OrderItem) BeforeCreate(tx *gorm.DB) error {
	if oi.ID == uuid.Nil {
		oi.ID = uuid.New()
	}
	return nil
}
