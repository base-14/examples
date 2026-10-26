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
	assert.NotNil(t, metrics.InputTokens)
	assert.NotNil(t, metrics.OutputTokens)
	assert.NotNil(t, metrics.InferenceDuration)
	assert.NotNil(t, metrics.Cost)
	assert.NotNil(t, metrics.RetryCount)
	assert.NotNil(t, metrics.FallbackCount)
	assert.NotNil(t, metrics.ErrorCount)
}

// TestGenAIMetricsRecord verifies the recorded metrics carry the OTel GenAI
// semantic-convention names, with input and output tokens on separate
// histograms and the semconv bucket boundaries. Fully in-memory, so no
// collector is required.
func TestGenAIMetricsRecord(t *testing.T) {
	ctx := context.Background()
	reader := sdkmetric.NewManualReader()
	mp := sdkmetric.NewMeterProvider(sdkmetric.WithReader(reader))
	t.Cleanup(func() { _ = mp.Shutdown(ctx) })

	metrics, err := NewGenAIMetrics(mp.Meter("test"))
	require.NoError(t, err)

	call := CallAttrs{Provider: "openai", Model: "gpt-4.1", Stage: "generate"}
	metrics.RecordInference(ctx, call, 1.5, 120, 45, "")
	metrics.RecordCost(ctx, call, 0.0021)

	collected := collect(t, reader)

	assert.Contains(t, collected, "base14.gen_ai.cost")
	assert.NotContains(t, collected, "gen_ai.client.token.usage")
	assert.NotContains(t, collected, "gen_ai.client.operation.duration")

	want := map[string]string{
		"gen_ai.operation.name": "chat",
		"gen_ai.provider.name":  "openai",
		"gen_ai.request.model":  "gpt-4.1",
		"base14.nlsql.stage":    "generate",
	}

	for name, value := range map[string]int64{
		"gen_ai.client.inference.operation.input_tokens":  120,
		"gen_ai.client.inference.operation.output_tokens": 45,
	} {
		m, ok := collected[name]
		require.True(t, ok, "%s must be recorded", name)
		assert.Equal(t, "{token}", m.Unit)
		hist, ok := m.Data.(metricdata.Histogram[int64])
		require.True(t, ok, "%s must be an int64 histogram", name)
		require.Len(t, hist.DataPoints, 1)
		dp := hist.DataPoints[0]
		assert.Equal(t, value, dp.Sum, name)
		assert.Equal(t, wantTokenBuckets, dp.Bounds, name)
		assertAttrs(t, dp.Attributes, want)
		_, present := dp.Attributes.Value(attribute.Key("gen_ai.token.type"))
		assert.False(t, present, "%s carries no gen_ai.token.type", name)
		_, present = dp.Attributes.Value(attribute.Key("error.type"))
		assert.False(t, present, "a successful call carries no error.type")
	}

	duration, ok := collected["gen_ai.client.inference.duration"]
	require.True(t, ok, "gen_ai.client.inference.duration must be recorded")
	assert.Equal(t, "s", duration.Unit)
	hist, ok := duration.Data.(metricdata.Histogram[float64])
	require.True(t, ok)
	require.Len(t, hist.DataPoints, 1)
	assert.Equal(t, 1.5, hist.DataPoints[0].Sum)
	assert.Equal(t, wantDurationBuckets, hist.DataPoints[0].Bounds)
	assertAttrs(t, hist.DataPoints[0].Attributes, want)
}

var wantTokenBuckets = []float64{1, 4, 16, 64, 256, 1024, 4096, 16384, 65536, 262144, 1048576, 4194304, 16777216, 67108864}

var wantDurationBuckets = []float64{0.01, 0.02, 0.04, 0.08, 0.16, 0.32, 0.64, 1.28, 2.56, 5.12, 10.24, 20.48, 40.96, 81.92}

func collect(t *testing.T, reader *sdkmetric.ManualReader) map[string]metricdata.Metrics {
	t.Helper()
	var rm metricdata.ResourceMetrics
	require.NoError(t, reader.Collect(context.Background(), &rm))

	collected := make(map[string]metricdata.Metrics)
	for _, sm := range rm.ScopeMetrics {
		for _, m := range sm.Metrics {
			collected[m.Name] = m
		}
	}
	return collected
}

func assertAttrs(t *testing.T, set attribute.Set, want map[string]string) {
	t.Helper()
	for key, value := range want {
		got, ok := set.Value(attribute.Key(key))
		require.True(t, ok, "missing attribute %s", key)
		assert.Equal(t, value, got.AsString(), "attribute %s", key)
	}
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
	call := CallAttrs{Provider: "openai", Model: "gpt-4.1"}
	metrics.RecordInference(ctx, call, 0.2, 10, 5, "")
	metrics.RecordCost(ctx, call, 0.0001)

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

// TestRecordInferenceOnFailure verifies the duration and token histograms
// are recorded on the failure path as well, carrying error.type, with zero
// tokens when no usage came back.
func TestRecordInferenceOnFailure(t *testing.T) {
	ctx := context.Background()
	reader := sdkmetric.NewManualReader()
	mp := sdkmetric.NewMeterProvider(sdkmetric.WithReader(reader))
	t.Cleanup(func() { _ = mp.Shutdown(ctx) })

	metrics, err := NewGenAIMetrics(mp.Meter("test"))
	require.NoError(t, err)

	call := CallAttrs{Provider: "ollama", Model: "qwen3.5:9B"}
	metrics.RecordInference(ctx, call, 0.4, 0, 0, "server_error")
	metrics.RecordError(ctx, call, "server_error")

	collected := collect(t, reader)
	want := map[string]string{
		"gen_ai.operation.name": "chat",
		"gen_ai.provider.name":  "ollama",
		"gen_ai.request.model":  "qwen3.5:9B",
		"error.type":            "server_error",
	}

	duration, ok := collected["gen_ai.client.inference.duration"]
	require.True(t, ok, "duration is recorded on failure")
	hist, ok := duration.Data.(metricdata.Histogram[float64])
	require.True(t, ok)
	require.Len(t, hist.DataPoints, 1)
	assertAttrs(t, hist.DataPoints[0].Attributes, want)

	for _, name := range []string{
		"gen_ai.client.inference.operation.input_tokens",
		"gen_ai.client.inference.operation.output_tokens",
	} {
		m, ok := collected[name]
		require.True(t, ok, "%s is recorded on failure", name)
		tokens, ok := m.Data.(metricdata.Histogram[int64])
		require.True(t, ok)
		require.Len(t, tokens.DataPoints, 1)
		assert.Equal(t, uint64(1), tokens.DataPoints[0].Count, name)
		assert.Equal(t, int64(0), tokens.DataPoints[0].Sum, name)
		assertAttrs(t, tokens.DataPoints[0].Attributes, want)
	}

	errorCount, ok := collected["base14.gen_ai.error.count"]
	require.True(t, ok, "base14.gen_ai.error.count is recorded")
	sum, ok := errorCount.Data.(metricdata.Sum[int64])
	require.True(t, ok)
	require.Len(t, sum.DataPoints, 1)
	provider, present := sum.DataPoints[0].Attributes.Value(attribute.Key("gen_ai.provider.name"))
	require.True(t, present, "the error count carries gen_ai.provider.name")
	assert.Equal(t, "ollama", provider.AsString())
}
