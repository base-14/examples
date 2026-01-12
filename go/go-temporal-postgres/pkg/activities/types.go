package activities

type OrderItem struct {
	ProductID string  `json:"product_id"`
	Quantity  int     `json:"quantity"`
	Price     float64 `json:"price"`
}

type ValidateOrderInput struct {
	OrderID     string      `json:"order_id"`
	CustomerID  string      `json:"customer_id"`
	TotalAmount float64     `json:"total_amount"`
	Items       []OrderItem `json:"items"`
}

type ValidateOrderResult struct {
	Valid  bool   `json:"valid"`
	Reason string `json:"reason,omitempty"`
}

type FraudAssessmentInput struct {
	OrderID      string  `json:"order_id"`
	CustomerID   string  `json:"customer_id"`
	CustomerTier string  `json:"customer_tier"`
	TotalAmount  float64 `json:"total_amount"`
}

type FraudAssessmentResult struct {
	RiskScore int    `json:"risk_score"`
	Reason    string `json:"reason,omitempty"`
}

type InventoryCheckInput struct {
	OrderID string      `json:"order_id"`
	Items   []OrderItem `json:"items"`
}

type InventoryCheckResult struct {
	AllAvailable     bool              `json:"all_available"`
	UnavailableItems []UnavailableItem `json:"unavailable_items,omitempty"`
}

type UnavailableItem struct {
	ProductID string `json:"product_id"`
	Requested int    `json:"requested"`
	Available int    `json:"available"`
}

type PaymentInput struct {
	OrderID    string  `json:"order_id"`
	CustomerID string  `json:"customer_id"`
	Amount     float64 `json:"amount"`
}

type PaymentResult struct {
	Success       bool   `json:"success"`
	TransactionID string `json:"transaction_id,omitempty"`
	Reason        string `json:"reason,omitempty"`
}

type ShippingInput struct {
	OrderID    string      `json:"order_id"`
	CustomerID string      `json:"customer_id"`
	Items      []OrderItem `json:"items"`
}

type ShippingResult struct {
	Reserved   bool   `json:"reserved"`
	TrackingID string `json:"tracking_id,omitempty"`
}

type NotificationInput struct {
	OrderID    string `json:"order_id"`
	CustomerID string `json:"customer_id"`
	Type       string `json:"type"`
	Message    string `json:"message"`
}

type RecordMetricsInput struct {
	OrderID       string  `json:"order_id"`
	CustomerTier  string  `json:"customer_tier"`
	DecisionPath  string  `json:"decision_path"`
	RiskScore     int     `json:"risk_score"`
	DurationSecs  float64 `json:"duration_secs"`
	FailureReason string  `json:"failure_reason,omitempty"`
}
