package simulation

import (
	"context"
	"crypto/rand"
	"errors"
	"math/big"
	"time"
)

var ErrSimulatedFailure = errors.New("simulated failure")

func cryptoRandFloat64() float64 {
	max := big.NewInt(1 << 53)
	n, err := rand.Int(rand.Reader, max)
	if err != nil {
		return 0.5
	}
	return float64(n.Int64()) / float64(1<<53)
}

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

func ShouldFail(rate float64) bool {
	if rate <= 0 {
		return false
	}
	if rate >= 1 {
		return true
	}
	return cryptoRandFloat64() < rate
}

func SimulateLatency(ctx context.Context, minMs, maxMs int) error {
	if minMs <= 0 && maxMs <= 0 {
		return nil
	}

	delayMs := minMs
	if maxMs > minMs {
		delayMs = minMs + cryptoRandIntn(maxMs-minMs)
	}

	if delayMs <= 0 {
		return nil
	}

	select {
	case <-time.After(time.Duration(delayMs) * time.Millisecond):
		return nil
	case <-ctx.Done():
		return ctx.Err()
	}
}

func MaybeFailWithLatency(ctx context.Context, cfg Config) error {
	if !cfg.Enabled {
		return nil
	}

	if err := SimulateLatency(ctx, cfg.MinLatencyMs, cfg.MaxLatencyMs); err != nil {
		return err
	}

	if ShouldFail(cfg.FailureRate) {
		return ErrSimulatedFailure
	}

	return nil
}

func RandomChoice[T any](choices []T) T {
	return choices[cryptoRandIntn(len(choices))]
}

func RandomInt(min, max int) int {
	if max <= min {
		return min
	}
	return min + cryptoRandIntn(max-min)
}

func RandomFloat(min, max float64) float64 {
	if max <= min {
		return min
	}
	return min + cryptoRandFloat64()*(max-min)
}
