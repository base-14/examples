package telemetry

import (
	"context"
	"net"
	"net/url"
	"os"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"go.opentelemetry.io/otel/attribute"
	sdkmetric "go.opentelemetry.io/otel/sdk/metric"
	"go.opentelemetry.io/otel/sdk/metric/metricdata"
)

// TestInitReturnsProvider verifies Init wires up valid providers and signal
// handles. Init performs no network I/O (OTLP HTTP exporters connect lazily),
// so this assertion is hermetic. Export happens only on Shutdown/flush, which
// depends on a live collector and is therefore not asserted here.
func TestInitReturnsProvider(t *testing.T) {
	ctx := context.Background()
	p, err := Init(ctx, "test-service", "http://localhost:4318", "test")
	require.NoError(t, err)
	assert.NotNil(t, p.Tracer)
	assert.NotNil(t, p.Meter)
	assert.NotNil(t, p.TracerProvider)
	assert.NotNil(t, p.MeterProvider)

	// Shutdown flushes pending telemetry to the collector. When none is
	// running the export fails; that is an environment condition, not a wiring
	// fault, so the result is intentionally not asserted.
	_ = p.Shutdown(ctx)
}

// TestGenAIMetricsInit verifies every GenAI instrument is constructed. Uses an
// in-memory ManualReader so it needs no collector.
func TestGenAIMetricsInit(t *testing.T) {
	mp := sdkmetric.NewMeterProvider(sdkmetric.WithReader(sdkmetric.NewManualReader()))
	t.Cleanup(func() { _ = mp.Shutdown(context.Background()) })

	metrics, err := NewGenAIMetrics(mp.Meter("test"))
	require.NoError(t, err)
	assert.NotNil(t, metrics.TokenUsage)
	assert.NotNil(t, metrics.OperationDuration)
	assert.NotNil(t, metrics.Cost)
	assert.NotNil(t, metrics.RetryCount)
	assert.NotNil(t, metrics.FallbackCount)
	assert.NotNil(t, metrics.ErrorCount)
}

// TestGenAIMetricsRecord verifies RecordGenAIMetrics emits the expected OTel
// GenAI semantic-convention metrics and splits token usage by input/output.
// Fully in-memory — no collector required.
func TestGenAIMetricsRecord(t *testing.T) {
	ctx := context.Background()
	reader := sdkmetric.NewManualReader()
	mp := sdkmetric.NewMeterProvider(sdkmetric.WithReader(reader))
	t.Cleanup(func() { _ = mp.Shutdown(ctx) })

	metrics, err := NewGenAIMetrics(mp.Meter("test"))
	require.NoError(t, err)

	metrics.RecordGenAIMetrics(ctx, RecordParams{
		Provider:     "openai",
		Model:        "gpt-4.1",
		Stage:        "generate",
		InputTokens:  120,
		OutputTokens: 45,
		DurationSec:  1.5,
		CostUSD:      0.0021,
	})

	var rm metricdata.ResourceMetrics
	require.NoError(t, reader.Collect(ctx, &rm))

	collected := make(map[string]metricdata.Metrics)
	for _, sm := range rm.ScopeMetrics {
		for _, m := range sm.Metrics {
			collected[m.Name] = m
		}
	}

	assert.Contains(t, collected, "gen_ai.client.operation.duration")
	assert.Contains(t, collected, "gen_ai.client.cost")

	tokenUsage, ok := collected["gen_ai.client.token.usage"]
	require.True(t, ok, "gen_ai.client.token.usage must be recorded")

	hist, ok := tokenUsage.Data.(metricdata.Histogram[float64])
	require.True(t, ok, "token usage must be a float64 histogram")

	byType := make(map[string]float64)
	for _, dp := range hist.DataPoints {
		typ, present := dp.Attributes.Value(attribute.Key("gen_ai.token.type"))
		require.True(t, present, "each token-usage point carries gen_ai.token.type")
		byType[typ.AsString()] = dp.Sum
	}
	assert.Equal(t, 120.0, byType["input"], "input tokens recorded under token.type=input")
	assert.Equal(t, 45.0, byType["output"], "output tokens recorded under token.type=output")
}

// TestOTLPExportIntegration exercises the real OTLP export path end to end
// against a live collector. It is opt-in: when no collector is reachable at the
// target endpoint the test skips rather than fails, so `make check` stays green
// without infrastructure while still verifying export when a collector is up.
func TestOTLPExportIntegration(t *testing.T) {
	endpoint := os.Getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
	if endpoint == "" {
		endpoint = "http://localhost:4318"
	}
	if !collectorReachable(endpoint) {
		t.Skipf("no OTLP collector reachable at %s; skipping export integration", endpoint)
	}

	ctx := context.Background()
	p, err := Init(ctx, "test-export", endpoint, "test")
	require.NoError(t, err)

	metrics, err := NewGenAIMetrics(p.Meter)
	require.NoError(t, err)
	metrics.RecordGenAIMetrics(ctx, RecordParams{
		Provider:     "openai",
		Model:        "gpt-4.1",
		InputTokens:  10,
		OutputTokens: 5,
		DurationSec:  0.2,
		CostUSD:      0.0001,
	})

	require.NoError(t, p.Shutdown(ctx), "flush/export to live collector should succeed")
}

func collectorReachable(endpoint string) bool {
	u, err := url.Parse(endpoint)
	if err != nil {
		return false
	}
	host := u.Host
	if u.Port() == "" {
		host = net.JoinHostPort(u.Hostname(), "4318")
	}
	conn, err := net.DialTimeout("tcp", host, 500*time.Millisecond)
	if err != nil {
		return false
	}
	_ = conn.Close()
	return true
}
