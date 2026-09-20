package llm

import (
	"context"
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"runtime"
	"testing"

	"ai-data-analyst/internal/config"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/codes"
	sdkmetric "go.opentelemetry.io/otel/sdk/metric"
	"go.opentelemetry.io/otel/sdk/metric/metricdata"
	"go.opentelemetry.io/otel/sdk/trace/tracetest"
	"go.opentelemetry.io/otel/trace"
)

// The vectors in _shared/test-vectors describe one chat call each, in terms of
// the span and metrics the call must produce. Every vector is replayed here
// against the in-memory span exporter and a manual metric reader.

type mockResponse struct {
	Content      string `json:"content"`
	InputTokens  int    `json:"input_tokens"`
	OutputTokens int    `json:"output_tokens"`
	Model        string `json:"model"`
	ResponseID   string `json:"response_id"`
	FinishReason string `json:"finish_reason"`
}

func (m mockResponse) response() *GenerateResponse {
	return &GenerateResponse{
		Content:      m.Content,
		Model:        m.Model,
		ResponseID:   m.ResponseID,
		InputTokens:  m.InputTokens,
		OutputTokens: m.OutputTokens,
		FinishReason: m.FinishReason,
	}
}

type expectedSpan struct {
	Name       string         `json:"name"`
	Status     string         `json:"status"`
	Attributes map[string]any `json:"attributes"`
	Events     []struct {
		Name string `json:"name"`
	} `json:"events"`
}

type expectedMetric struct {
	Name  string         `json:"name"`
	Value float64        `json:"value"`
	Attrs map[string]any `json:"attrs"`
}

func testConfig() *config.Config {
	return &config.Config{OllamaBaseURL: "http://localhost:11434"}
}

func loadVector(t *testing.T, name string, into any) {
	t.Helper()
	_, thisFile, _, ok := runtime.Caller(0)
	require.True(t, ok)
	path := filepath.Join(filepath.Dir(thisFile), "..", "..", "..", "..", "_shared", "test-vectors", name)

	data, err := os.ReadFile(path)
	require.NoError(t, err, "test vector %s must be readable", name)
	require.NoError(t, json.Unmarshal(data, into))
}

// providerFor returns a mock that reports the real provider's server address
// and port, so the vector's expectations cover the provider table without
// calling any provider.
func providerFor(t *testing.T, configKey string, resp *GenerateResponse) *mockProvider {
	t.Helper()
	real, err := NewProvider(configKey, testConfig())
	require.NoError(t, err)
	return &mockProvider{
		name:    configKey,
		address: real.ServerAddress(),
		port:    real.ServerPort(),
		resp:    resp,
	}
}

func assertSpanAttributes(t *testing.T, span tracetest.SpanStub, expected map[string]any) {
	t.Helper()
	for key, want := range expected {
		got := requireAttr(t, span, key)
		switch v := want.(type) {
		case string:
			assert.Equal(t, v, got.AsString(), "attribute %s", key)
		case bool:
			assert.Equal(t, v, got.AsBool(), "attribute %s", key)
		case float64:
			if got.Type() == attribute.INT64 {
				assert.Equal(t, int64(v), got.AsInt64(), "attribute %s", key)
			} else {
				assert.InDelta(t, v, got.AsFloat64(), v*0.01+1e-9, "attribute %s", key)
			}
		case []any:
			strs := make([]string, len(v))
			for i, item := range v {
				strs[i] = item.(string)
			}
			assert.Equal(t, strs, got.AsStringSlice(), "attribute %s", key)
		default:
			t.Fatalf("vector attribute %s has unsupported type %T", key, want)
		}
	}
}

func matchesAttrs(point attribute.Set, want map[string]any) bool {
	for key, expected := range want {
		value, ok := point.Value(attribute.Key(key))
		if !ok {
			return false
		}
		switch v := expected.(type) {
		case string:
			if value.AsString() != v {
				return false
			}
		case float64:
			if value.Type() == attribute.INT64 {
				if value.AsInt64() != int64(v) {
					return false
				}
			} else if value.AsFloat64() != v {
				return false
			}
		default:
			return false
		}
	}
	return true
}

// metricTotal sums every point of a counter or histogram whose attributes
// contain want.
func metricTotal(t *testing.T, reader *sdkmetric.ManualReader, name string, want map[string]any) float64 {
	t.Helper()
	total := 0.0
	for _, m := range collectMetrics(t, reader, name) {
		switch data := m.Data.(type) {
		case metricdata.Sum[int64]:
			for _, dp := range data.DataPoints {
				if matchesAttrs(dp.Attributes, want) {
					total += float64(dp.Value)
				}
			}
		case metricdata.Sum[float64]:
			for _, dp := range data.DataPoints {
				if matchesAttrs(dp.Attributes, want) {
					total += dp.Value
				}
			}
		case metricdata.Histogram[float64]:
			for _, dp := range data.DataPoints {
				if matchesAttrs(dp.Attributes, want) {
					total += dp.Sum
				}
			}
		}
	}
	return total
}

// metricCount counts histogram observations whose attributes contain want.
func metricCount(t *testing.T, reader *sdkmetric.ManualReader, name string, want map[string]any) uint64 {
	t.Helper()
	var count uint64
	for _, m := range collectMetrics(t, reader, name) {
		if hist, ok := m.Data.(metricdata.Histogram[float64]); ok {
			for _, dp := range hist.DataPoints {
				if matchesAttrs(dp.Attributes, want) {
					count += dp.Count
				}
			}
		}
	}
	return count
}

func collectMetrics(t *testing.T, reader *sdkmetric.ManualReader, name string) []metricdata.Metrics {
	t.Helper()
	var rm metricdata.ResourceMetrics
	require.NoError(t, reader.Collect(context.Background(), &rm))

	var out []metricdata.Metrics
	for _, sm := range rm.ScopeMetrics {
		for _, m := range sm.Metrics {
			if m.Name == name {
				out = append(out, m)
			}
		}
	}
	return out
}

func metricExists(t *testing.T, reader *sdkmetric.ManualReader, name string) bool {
	t.Helper()
	return len(collectMetrics(t, reader, name)) > 0
}

func TestChatCompletionVector(t *testing.T) {
	var vector struct {
		Input struct {
			Provider    string  `json:"provider"`
			Model       string  `json:"model"`
			Prompt      string  `json:"prompt"`
			System      string  `json:"system"`
			Temperature float64 `json:"temperature"`
			MaxTokens   int     `json:"max_tokens"`
		} `json:"input"`
		MockResponse mockResponse `json:"mock_response"`
		ExpectedSpan expectedSpan `json:"expected_span"`
	}
	loadVector(t, "chat-completion.json", &vector)

	primary := providerFor(t, vector.Input.Provider, vector.MockResponse.response())
	client, rec := newTestClient(t, primary, nil)

	resp, err := client.Generate(context.Background(), GenerateRequest{
		Model:       vector.Input.Model,
		System:      vector.Input.System,
		Prompt:      vector.Input.Prompt,
		Temperature: vector.Input.Temperature,
		MaxTokens:   vector.Input.MaxTokens,
	})
	require.NoError(t, err)
	assert.Equal(t, vector.MockResponse.Content, resp.Content)

	span := rec.span(t, vector.ExpectedSpan.Name)
	assert.Equal(t, trace.SpanKindClient, span.SpanKind)
	assert.NotEqual(t, codes.Error, span.Status.Code)
	assertSpanAttributes(t, span, vector.ExpectedSpan.Attributes)
	assert.Empty(t, span.Events, "the inference event needs content capture, which is off by default")

	base := map[string]any{
		"gen_ai.operation.name": "chat",
		"gen_ai.provider.name":  vector.Input.Provider,
		"gen_ai.request.model":  vector.Input.Model,
	}
	input := map[string]any{"gen_ai.token.type": "input"}
	output := map[string]any{"gen_ai.token.type": "output"}
	for k, v := range base {
		input[k] = v
		output[k] = v
	}

	assert.Equal(t, float64(vector.MockResponse.InputTokens), metricTotal(t, rec.metrics, "gen_ai.client.token.usage", input))
	assert.Equal(t, float64(vector.MockResponse.OutputTokens), metricTotal(t, rec.metrics, "gen_ai.client.token.usage", output))
	assert.Equal(t, uint64(1), metricCount(t, rec.metrics, "gen_ai.client.operation.duration", base))
	assert.InDelta(t, vector.ExpectedSpan.Attributes["base14.gen_ai.cost_usd"].(float64),
		metricTotal(t, rec.metrics, "base14.gen_ai.cost", base), 1e-9)

	assert.False(t, metricExists(t, rec.metrics, "base14.gen_ai.retry.count"), "no retries on success")
	assert.False(t, metricExists(t, rec.metrics, "base14.gen_ai.fallback.count"), "no fallback on success")
	assert.False(t, metricExists(t, rec.metrics, "base14.gen_ai.error.count"), "no errors on success")
}

func TestChatWithRetryVector(t *testing.T) {
	var vector struct {
		Setup struct {
			Provider string `json:"provider"`
			Model    string `json:"model"`
		} `json:"setup"`
		MockBehavior struct {
			Attempt2 mockResponse `json:"attempt_2"`
		} `json:"mock_behavior"`
		ExpectedSpan    expectedSpan     `json:"expected_span"`
		ExpectedMetrics []expectedMetric `json:"expected_metrics"`
	}
	loadVector(t, "chat-with-retry.json", &vector)

	primary := providerFor(t, vector.Setup.Provider, vector.MockBehavior.Attempt2.response())
	primary.failN = 1
	primary.failErr = errors.New("Rate limit")

	client, rec := newTestClient(t, primary, nil)
	resp, err := client.Generate(context.Background(), GenerateRequest{
		Model:  vector.Setup.Model,
		System: "You are helpful.",
		Prompt: "Hello",
	})
	require.NoError(t, err)
	assert.Equal(t, vector.MockBehavior.Attempt2.Content, resp.Content)
	assert.Equal(t, 2, primary.calls)

	span := rec.span(t, vector.ExpectedSpan.Name)
	assert.NotEqual(t, codes.Error, span.Status.Code, "a retry that succeeds stays invisible to the caller")
	assertSpanAttributes(t, span, vector.ExpectedSpan.Attributes)

	retry := vectorMetric(t, vector.ExpectedMetrics, "base14.gen_ai.retry.count")
	// The vector names the error by its Python exception class. This client
	// classifies failures by kind instead, so error.type is asserted against
	// the classifier.
	retryAttrs := map[string]any{
		"gen_ai.provider.name": vector.Setup.Provider,
		"error.type":           "rate_limit",
		"base14.retry.attempt": retry.Attrs["base14.retry.attempt"],
	}
	assert.Equal(t, retry.Value, metricTotal(t, rec.metrics, "base14.gen_ai.retry.count", retryAttrs))

	assert.False(t, metricExists(t, rec.metrics, "base14.gen_ai.fallback.count"), "a successful retry needs no fallback")
	assert.False(t, metricExists(t, rec.metrics, "base14.gen_ai.error.count"), "a successful retry is not an error")
}

func TestChatWithFallbackVector(t *testing.T) {
	var vector struct {
		Setup struct {
			PrimaryProvider  string `json:"primary_provider"`
			PrimaryModel     string `json:"primary_model"`
			FallbackProvider string `json:"fallback_provider"`
			FallbackModel    string `json:"fallback_model"`
		} `json:"setup"`
		MockBehavior struct {
			Fallback mockResponse `json:"fallback"`
		} `json:"mock_behavior"`
		ExpectedSpans   []expectedSpan   `json:"expected_spans"`
		ExpectedMetrics []expectedMetric `json:"expected_metrics"`
	}
	loadVector(t, "chat-with-fallback.json", &vector)

	primary := providerFor(t, vector.Setup.PrimaryProvider, nil)
	primary.failN = 10
	primary.failErr = errors.New("Service unavailable")
	fallback := providerFor(t, vector.Setup.FallbackProvider, vector.MockBehavior.Fallback.response())

	client, rec := newTestClient(t, primary, fallback)
	client.FallbackModel = vector.Setup.FallbackModel

	ctx, parent := client.Tracer.Start(context.Background(), "pipeline ask")
	resp, err := client.Generate(ctx, GenerateRequest{
		Model:  vector.Setup.PrimaryModel,
		System: "You are helpful.",
		Prompt: "Hello",
	})
	parent.End()

	require.NoError(t, err)
	assert.Equal(t, vector.MockBehavior.Fallback.Content, resp.Content)
	assert.Equal(t, 3, primary.calls, "the primary is retried to exhaustion before the switch")
	assert.Equal(t, 1, fallback.calls)

	primarySpan := rec.span(t, vector.ExpectedSpans[0].Name)
	assert.Equal(t, codes.Error, primarySpan.Status.Code)
	assert.Equal(t, vector.ExpectedSpans[0].Attributes["gen_ai.provider.name"],
		requireAttr(t, primarySpan, "gen_ai.provider.name").AsString())
	assert.Equal(t, "unknown_error", requireAttr(t, primarySpan, "error.type").AsString())

	fallbackSpan := rec.span(t, vector.ExpectedSpans[1].Name)
	assert.NotEqual(t, codes.Error, fallbackSpan.Status.Code)
	assertSpanAttributes(t, fallbackSpan, vector.ExpectedSpans[1].Attributes)

	parentSpan := rec.span(t, "pipeline ask")
	assert.NotEqual(t, codes.Error, parentSpan.Status.Code, "a recovered call leaves the caller healthy")
	assert.True(t, requireAttr(t, parentSpan, "gen_ai.fallback.triggered").AsBool())

	var found bool
	for _, e := range parentSpan.Events {
		if e.Name != "provider_fallback" {
			continue
		}
		found = true
		attrs := map[string]string{}
		for _, kv := range e.Attributes {
			attrs[string(kv.Key)] = kv.Value.AsString()
		}
		assert.Equal(t, vector.Setup.PrimaryProvider, attrs["gen_ai.provider.name"])
		assert.Equal(t, vector.Setup.FallbackProvider, attrs["base14.gen_ai.fallback.provider"])
	}
	assert.True(t, found, "the calling span carries a provider_fallback event")

	retry := vectorMetric(t, vector.ExpectedMetrics, "base14.gen_ai.retry.count")
	assert.Equal(t, retry.Value, metricTotal(t, rec.metrics, "base14.gen_ai.retry.count", nil),
		"the attempt that exhausts the budget is not counted as a retry")

	fallbackMetric := vectorMetric(t, vector.ExpectedMetrics, "base14.gen_ai.fallback.count")
	assert.Equal(t, fallbackMetric.Value, metricTotal(t, rec.metrics, "base14.gen_ai.fallback.count", map[string]any{
		"gen_ai.provider.name":            vector.Setup.PrimaryProvider,
		"base14.gen_ai.fallback.provider": vector.Setup.FallbackProvider,
	}))

	errorMetric := vectorMetric(t, vector.ExpectedMetrics, "base14.gen_ai.error.count")
	assert.Equal(t, errorMetric.Value, metricTotal(t, rec.metrics, "base14.gen_ai.error.count", map[string]any{
		"gen_ai.provider.name": vector.Setup.PrimaryProvider,
	}))

	fallbackTokens := map[string]any{"gen_ai.request.model": vector.Setup.FallbackModel, "gen_ai.token.type": "input"}
	assert.Equal(t, float64(vector.MockBehavior.Fallback.InputTokens),
		metricTotal(t, rec.metrics, "gen_ai.client.token.usage", fallbackTokens))
	assert.Greater(t, metricTotal(t, rec.metrics, "base14.gen_ai.cost",
		map[string]any{"gen_ai.request.model": vector.Setup.FallbackModel}), 0.0)
	assert.Equal(t, 0.0, metricTotal(t, rec.metrics, "gen_ai.client.token.usage",
		map[string]any{"gen_ai.request.model": vector.Setup.PrimaryModel}),
		"the failed primary records no token usage")
}

func vectorMetric(t *testing.T, metrics []expectedMetric, name string) expectedMetric {
	t.Helper()
	for _, m := range metrics {
		if m.Name == name {
			return m
		}
	}
	t.Fatalf("vector has no expectation for metric %q", name)
	return expectedMetric{}
}
