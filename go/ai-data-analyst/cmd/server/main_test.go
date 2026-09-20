package main

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
)

func TestRetryConnect(t *testing.T) {
	refused := errors.New("connection refused")
	tests := []struct {
		name         string
		failures     int
		window       time.Duration
		wantAttempts int
		wantErr      error
	}{
		{"first attempt succeeds", 0, 100 * time.Millisecond, 1, nil},
		{"succeeds after two refusals", 2, 100 * time.Millisecond, 3, nil},
		{"gives up after the window", 100, 25 * time.Millisecond, 2, refused},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			attempts := 0
			dial := func(ctx context.Context, databaseURL string) (*pgxpool.Pool, error) {
				attempts++
				if attempts <= tt.failures {
					return nil, refused
				}
				return &pgxpool.Pool{}, nil
			}
			pool, err := retryConnect(context.Background(), "postgres://x", dial, tt.window, 10*time.Millisecond)
			if !errors.Is(err, tt.wantErr) {
				t.Fatalf("err = %v, want %v", err, tt.wantErr)
			}
			if err == nil && pool == nil {
				t.Fatal("pool is nil on success")
			}
			if err == nil && attempts != tt.wantAttempts {
				t.Fatalf("attempts = %d, want %d", attempts, tt.wantAttempts)
			}
			if err != nil && attempts < tt.wantAttempts {
				t.Fatalf("attempts = %d, want at least %d", attempts, tt.wantAttempts)
			}
		})
	}
}
