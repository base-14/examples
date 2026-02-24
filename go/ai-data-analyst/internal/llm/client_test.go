package llm

import (
	"context"
	"errors"
	"testing"

	"ai-data-analyst/internal/telemetry"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
	"go.opentelemetry.io/otel/sdk/trace/tracetest"
)

type mockProvider struct {
	name    string
	calls   int
	failN   int
	resp    *GenerateResponse
	failErr error
}

func (m *mockProvider) Name() string { return m.name }

func (m *mockProvider) Generate(_ context.Context, _ GenerateRequest) (*GenerateResponse, error) {
	m.calls++
	if m.calls <= m.failN {
		return nil, m.failErr
	}
	return m.resp, nil
}

func newTestClient(t *testing.T, primary, fallback Provider) (*Client, *tracetest.InMemoryExporter) {
	t.Helper()
	exporter := tracetest.NewInMemoryExporter()
	tp := sdktrace.NewTracerProvider(sdktrace.WithSyncer(exporter))
	tracer := tp.Tracer("test")

	p, err := telemetry.Init(context.Background(), "test", "http://localhost:4318", "test")
	require.NoError(t, err)
	metrics, err := telemetry.NewGenAIMetrics(p.Meter)
	require.NoError(t, err)

	primaryName := "openai"
	fallbackName := ""
	if primary != nil {
		primaryName = primary.Name()
	}
	if fallback != nil {
		fallbackName = fallback.Name()
	}

	return &Client{
		Primary:              primary,
		Fallback:             fallback,
		Tracer:               tracer,
		Metrics:              metrics,
		PrimaryProvider:      primaryName,
		FallbackProviderName: fallbackName,
	}, exporter
}

func testReq() GenerateRequest {
	return GenerateRequest{
		Model:       "gpt-4.1",
		System:      "You are a test assistant.",
		Prompt:      "Say hello",
		Temperature: 0.1,
		MaxTokens:   100,
		Stage:       "generate",
	}
}

func TestGenerateOnceSuccess(t *testing.T) {
	primary := &mockProvider{
		name: "openai",
		resp: &GenerateResponse{
			Content:      "Hello!",
			Model:        "gpt-4.1",
			InputTokens:  10,
			OutputTokens: 5,
		},
	}
	client, exporter := newTestClient(t, primary, nil)
	req := testReq()

	resp, err := client.GenerateOnce(context.Background(), primary, "openai", req)
	require.NoError(t, err)
	assert.Equal(t, "Hello!", resp.Content)
	assert.Equal(t, "gpt-4.1", resp.Model)
	assert.Greater(t, resp.CostUSD, 0.0)
	assert.Equal(t, 1, primary.calls)

	spans := exporter.GetSpans()
	assert.Len(t, spans, 1)
	assert.Equal(t, "gen_ai.chat gpt-4.1", spans[0].Name)
}

func TestGenerateWithRetrySuccess(t *testing.T) {
	primary := &mockProvider{
		name:    "openai",
		failN:   2,
		failErr: errors.New("rate limit"),
		resp: &GenerateResponse{
			Content:      "Hello!",
			Model:        "gpt-4.1",
			InputTokens:  10,
			OutputTokens: 5,
		},
	}
	client, _ := newTestClient(t, primary, nil)

	resp, err := client.GenerateWithRetry(context.Background(), primary, "openai", testReq())
	require.NoError(t, err)
	assert.Equal(t, "Hello!", resp.Content)
	assert.Equal(t, 3, primary.calls)
}

func TestGenerateWithRetryAllFail(t *testing.T) {
	primary := &mockProvider{
		name:    "openai",
		failN:   10,
		failErr: errors.New("always fails"),
	}
	client, _ := newTestClient(t, primary, nil)

	_, err := client.GenerateWithRetry(context.Background(), primary, "openai", testReq())
	assert.Error(t, err)
	assert.Equal(t, 3, primary.calls)
}

func TestGenerateWithFallback(t *testing.T) {
	primary := &mockProvider{
		name:    "openai",
		failN:   10,
		failErr: errors.New("primary down"),
	}
	fallback := &mockProvider{
		name: "anthropic",
		resp: &GenerateResponse{
			Content:      "Fallback response",
			Model:        "claude-haiku-4-5-20251001",
			InputTokens:  10,
			OutputTokens: 5,
		},
	}
	client, _ := newTestClient(t, primary, fallback)

	resp, err := client.Generate(context.Background(), testReq())
	require.NoError(t, err)
	assert.Equal(t, "Fallback response", resp.Content)
	assert.Equal(t, 3, primary.calls)
	assert.Equal(t, 1, fallback.calls)
}

func TestGenerateNoFallbackReturnsError(t *testing.T) {
	primary := &mockProvider{
		name:    "openai",
		failN:   10,
		failErr: errors.New("always fails"),
	}
	client, _ := newTestClient(t, primary, nil)

	_, err := client.Generate(context.Background(), testReq())
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "primary provider")
}
