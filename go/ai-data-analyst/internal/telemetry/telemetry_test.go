package telemetry

import (
	"context"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestInitReturnsProvider(t *testing.T) {
	ctx := context.Background()
	// Uses default endpoint — will fail to export but should not error on init
	p, err := Init(ctx, "test-service", "http://localhost:4318", "test")
	require.NoError(t, err)
	assert.NotNil(t, p.Tracer)
	assert.NotNil(t, p.Meter)
	assert.NotNil(t, p.TracerProvider)
	assert.NotNil(t, p.MeterProvider)

	require.NoError(t, p.Shutdown(ctx))
}

func TestGenAIMetricsInit(t *testing.T) {
	ctx := context.Background()
	p, err := Init(ctx, "test-metrics", "http://localhost:4318", "test")
	require.NoError(t, err)
	defer p.Shutdown(ctx)

	metrics, err := NewGenAIMetrics(p.Meter)
	require.NoError(t, err)
	assert.NotNil(t, metrics.TokenUsage)
	assert.NotNil(t, metrics.Cost)
	assert.NotNil(t, metrics.RetryCount)
	assert.NotNil(t, metrics.FallbackCount)
	assert.NotNil(t, metrics.ErrorCount)
}
