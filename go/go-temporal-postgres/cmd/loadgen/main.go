package main

import (
	"bytes"
	"context"
	"crypto/rand"
	"encoding/json"
	"flag"
	"fmt"
	"log/slog"
	"math/big"
	"net/http"
	"os"
	"sync"
	"sync/atomic"
	"time"
)

func cryptoRandIntn(max int) int {
	if max <= 0 {
		return 0
	}
	n, err := rand.Int(rand.Reader, big.NewInt(int64(max)))
	if err != nil {
		return 0
	}
	return int(n.Int64())
}

func cryptoRandFloat64() float64 {
	max := big.NewInt(1 << 53)
	n, err := rand.Int(rand.Reader, max)
	if err != nil {
		return 0.5
	}
	return float64(n.Int64()) / float64(1<<53)
}

type OrderRequest struct {
	CustomerID   string      `json:"customer_id"`
	CustomerTier string      `json:"customer_tier"`
	Items        []OrderItem `json:"items"`
}

type OrderItem struct {
	ProductID string  `json:"product_id"`
	Quantity  int     `json:"quantity"`
	Price     float64 `json:"price"`
}

type product struct {
	ID     string
	Price  float64
	Weight float64 // higher weight = more frequent
}

var (
	customerTiers = []string{"standard", "silver", "gold", "platinum"}

	// Products with INR prices (₹50,000 to ₹25,00,000 range)
	// Weights control frequency: higher weight = more common
	products = []product{
		// Low value (₹50,000 - ₹1,00,000) - most common (60%)
		{"electronics-basic", 52000, 20},
		{"furniture-chair", 65000, 15},
		{"appliance-small", 78000, 15},
		{"gadget-tablet", 95000, 10},

		// Medium value (₹1,00,000 - ₹5,00,000) - common (30%)
		{"electronics-laptop", 125000, 8},
		{"furniture-sofa", 185000, 7},
		{"appliance-ac", 275000, 6},
		{"jewelry-gold", 450000, 5},
		{"electronics-tv", 350000, 4},

		// High value (₹5,00,000 - ₹15,00,000) - less common (8%)
		{"jewelry-diamond", 750000, 3},
		{"vehicle-bike", 950000, 2},
		{"furniture-set", 1200000, 2},
		{"electronics-premium", 1450000, 1},

		// Very high value (₹15,00,000 - ₹25,00,000) - rare (2%)
		{"vehicle-car", 1800000, 1},
		{"jewelry-luxury", 2200000, 0.5},
		{"art-collectible", 2500000, 0.5},
	}

	totalWeight float64
)

func init() {
	for _, p := range products {
		totalWeight += p.Weight
	}
}

func main() {
	defaultURL := os.Getenv("API_URL")
	if defaultURL == "" {
		defaultURL = "http://localhost:8080/api/orders"
	}

	var (
		apiURL   = flag.String("url", defaultURL, "API endpoint URL")
		count    = flag.Int("count", 0, "Number of orders to generate (0 = unlimited)")
		rps      = flag.Float64("rps", 1, "Requests per second")
		duration = flag.Duration("duration", 0, "Duration to run (0 = until count reached or forever)")
		workers  = flag.Int("workers", 5, "Number of concurrent workers")
	)
	flag.Parse()

	if *count == 0 && *duration == 0 {
		slog.Error("must specify either --count or --duration")
		os.Exit(1)
	}

	slog.Info("starting load generator",
		slog.String("url", *apiURL),
		slog.Int("count", *count),
		slog.Float64("rps", *rps),
		slog.Duration("duration", *duration),
		slog.Int("workers", *workers),
	)

	var (
		successCount int64
		failureCount int64
		totalCount   int64
		startTime    = time.Now()
		stopCh       = make(chan struct{})
		orderCh      = make(chan OrderRequest, *workers*2)
		wg           sync.WaitGroup
	)

	for i := 0; i < *workers; i++ {
		wg.Add(1)
		go func(workerID int) {
			defer wg.Done()
			client := &http.Client{Timeout: 30 * time.Second}

			for order := range orderCh {
				if err := submitOrder(context.Background(), client, *apiURL, order); err != nil {
					atomic.AddInt64(&failureCount, 1)
					slog.Error("order failed",
						slog.Int("worker", workerID),
						slog.String("customer_id", order.CustomerID),
						slog.String("error", err.Error()),
					)
				} else {
					atomic.AddInt64(&successCount, 1)
					slog.Debug("order submitted",
						slog.Int("worker", workerID),
						slog.String("customer_id", order.CustomerID),
					)
				}
			}
		}(i)
	}

	if *duration > 0 {
		go func() {
			time.Sleep(*duration)
			close(stopCh)
		}()
	}

	interval := time.Duration(float64(time.Second) / *rps)
	ticker := time.NewTicker(interval)
	defer ticker.Stop()

	for {
		select {
		case <-stopCh:
			goto done
		case <-ticker.C:
			if *count > 0 && atomic.LoadInt64(&totalCount) >= int64(*count) {
				goto done
			}

			atomic.AddInt64(&totalCount, 1)
			order := generateOrder(atomic.LoadInt64(&totalCount))
			orderCh <- order
		}
	}

done:
	close(orderCh)
	wg.Wait()

	elapsed := time.Since(startTime)
	success := atomic.LoadInt64(&successCount)
	failure := atomic.LoadInt64(&failureCount)
	total := success + failure

	slog.Info("load generation complete",
		slog.Int64("total", total),
		slog.Int64("success", success),
		slog.Int64("failure", failure),
		slog.Float64("success_rate", float64(success)/float64(total)*100),
		slog.Duration("elapsed", elapsed),
		slog.Float64("actual_rps", float64(total)/elapsed.Seconds()),
	)
}

func generateOrder(seq int64) OrderRequest {
	customerID := fmt.Sprintf("cust-%d-%d", seq, cryptoRandIntn(1000))
	tier := customerTiers[cryptoRandIntn(len(customerTiers))]

	numItems := 1 + cryptoRandIntn(3)
	items := make([]OrderItem, numItems)
	for i := 0; i < numItems; i++ {
		p := selectWeightedProduct()
		items[i] = OrderItem{
			ProductID: p.ID,
			Quantity:  1 + cryptoRandIntn(2), // 1-2 quantity for high value items
			Price:     p.Price,
		}
	}

	return OrderRequest{
		CustomerID:   customerID,
		CustomerTier: tier,
		Items:        items,
	}
}

func selectWeightedProduct() product {
	r := cryptoRandFloat64() * totalWeight
	cumulative := 0.0
	for _, p := range products {
		cumulative += p.Weight
		if r <= cumulative {
			return p
		}
	}
	return products[0]
}

func submitOrder(ctx context.Context, client *http.Client, url string, order OrderRequest) error {
	body, err := json.Marshal(order)
	if err != nil {
		return fmt.Errorf("marshal error: %w", err)
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, url, bytes.NewReader(body))
	if err != nil {
		return fmt.Errorf("request creation error: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := client.Do(req)
	if err != nil {
		return fmt.Errorf("request error: %w", err)
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode >= 400 {
		return fmt.Errorf("API error: status %d", resp.StatusCode)
	}

	return nil
}
