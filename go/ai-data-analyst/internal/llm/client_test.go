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
	name      string
	calls     int
	failN     int
	resp      *GenerateResponse
	failErr   error
	lastModel string
}

func (m *mockProvider) Name() string { return m.name }

func (m *mockProvider) Generate(_ context.Context, req GenerateRequest) (*GenerateResponse, error) {
	m.calls++
	m.lastModel = req.Model
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

	fallbackModel := ""
	if fallback != nil {
		fallbackModel = "claude-haiku-4-5-20251001"
	}

	return &Client{
		Primary:              primary,
		Fallback:             fallback,
		Tracer:               tracer,
		Metrics:              metrics,
		PrimaryProvider:      primaryName,
		FallbackProviderName: fallbackName,
		FallbackModel:        fallbackModel,
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
	assert.Equal(t, "claude-haiku-4-5-20251001", fallback.lastModel, "fallback should use FallbackModel, not the primary model")
}

func TestClassifyError(t *testing.T) {
	tests := []struct {
		name     string
		err      error
		expected string
	}{
		{"rate limit message", errors.New("rate limit exceeded"), "rate_limit"},
		{"HTTP 429", errors.New("status 429: too many requests"), "rate_limit"},
		{"timeout", errors.New("context deadline exceeded: timeout"), "timeout"},
		{"deadline", errors.New("context deadline exceeded"), "timeout"},
		{"HTTP 401", errors.New("401 unauthorized"), "auth_error"},
		{"HTTP 403", errors.New("403 forbidden"), "auth_error"},
		{"auth keyword", errors.New("authentication failed"), "auth_error"},
		{"api key", errors.New("invalid api key"), "auth_error"},
		{"HTTP 400", errors.New("400 bad request"), "invalid_request"},
		{"HTTP 422", errors.New("422 unprocessable entity"), "invalid_request"},
		{"invalid keyword", errors.New("invalid model name"), "invalid_request"},
		{"HTTP 500", errors.New("500 internal server error"), "server_error"},
		{"HTTP 502", errors.New("502 bad gateway"), "server_error"},
		{"HTTP 503", errors.New("503 service unavailable"), "server_error"},
		{"connection refused", errors.New("dial tcp: connect refused"), "network_error"},
		{"dns failure", errors.New("dns resolution failed"), "network_error"},
		{"connection reset", errors.New("connection reset by peer"), "network_error"},
		{"unknown error", errors.New("something unexpected"), "unknown_error"},
		{"nil error", nil, "unknown_error"},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			assert.Equal(t, tt.expected, classifyError(tt.err))
		})
	}
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
