package llm

import (
	"context"
	"errors"
	"testing"

	"ai-data-analyst/internal/telemetry"

	"github.com/cenkalti/backoff/v5"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/codes"
	sdkmetric "go.opentelemetry.io/otel/sdk/metric"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
	"go.opentelemetry.io/otel/sdk/trace/tracetest"
	"go.opentelemetry.io/otel/trace"
)

type mockProvider struct {
	name      string
	address   string
	port      int
	calls     int
	failN     int
	resp      *GenerateResponse
	failErr   error
	lastModel string
}

func (m *mockProvider) Name() string { return m.name }

func (m *mockProvider) ServerAddress() string { return m.address }

func (m *mockProvider) ServerPort() int { return m.port }

func (m *mockProvider) Generate(_ context.Context, req GenerateRequest) (*GenerateResponse, error) {
	m.calls++
	m.lastModel = req.Model
	if m.calls <= m.failN {
		return nil, m.failErr
	}
	return m.resp, nil
}

type recorded struct {
	spans   *tracetest.InMemoryExporter
	metrics *sdkmetric.ManualReader
}

// newTestClient wires a client to in-memory span and metric readers, with the
// retry wait removed so the suite does not sleep.
func newTestClient(t *testing.T, primary, fallback Provider) (*Client, *recorded) {
	t.Helper()

	exporter := tracetest.NewInMemoryExporter()
	tp := sdktrace.NewTracerProvider(sdktrace.WithSyncer(exporter))
	t.Cleanup(func() { _ = tp.Shutdown(context.Background()) })

	reader := sdkmetric.NewManualReader()
	mp := sdkmetric.NewMeterProvider(sdkmetric.WithReader(reader))
	t.Cleanup(func() { _ = mp.Shutdown(context.Background()) })

	metrics, err := telemetry.NewGenAIMetrics(mp.Meter("test"))
	require.NoError(t, err)

	fallbackModel := ""
	if fallback != nil {
		fallbackModel = "claude-haiku-4-5-20251001"
	}

	client := &Client{
		Primary:       primary,
		Fallback:      fallback,
		FallbackModel: fallbackModel,
		Tracer:        tp.Tracer("test"),
		Metrics:       metrics,
		Backoff:       &backoff.ZeroBackOff{},
	}
	return client, &recorded{spans: exporter, metrics: reader}
}

func (r *recorded) span(t *testing.T, name string) tracetest.SpanStub {
	t.Helper()
	var names []string
	for _, s := range r.spans.GetSpans() {
		if s.Name == name {
			return s
		}
		names = append(names, s.Name)
	}
	t.Fatalf("span %q not found in %v", name, names)
	return tracetest.SpanStub{}
}

func spanAttr(s tracetest.SpanStub, key string) (attribute.Value, bool) {
	for _, kv := range s.Attributes {
		if string(kv.Key) == key {
			return kv.Value, true
		}
	}
	return attribute.Value{}, false
}

func requireAttr(t *testing.T, s tracetest.SpanStub, key string) attribute.Value {
	t.Helper()
	v, ok := spanAttr(s, key)
	require.True(t, ok, "span %q is missing attribute %q", s.Name, key)
	return v
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

func openAIMock() *mockProvider {
	return &mockProvider{
		name:    "openai",
		address: "api.openai.com",
		port:    443,
		resp: &GenerateResponse{
			Content:      "Hello!",
			Model:        "gpt-4.1",
			ResponseID:   "chatcmpl_test",
			InputTokens:  10,
			OutputTokens: 5,
			FinishReason: "stop",
		},
	}
}

func TestChatSpanCarriesGenAIAttributes(t *testing.T) {
	primary := openAIMock()
	client, rec := newTestClient(t, primary, nil)

	resp, err := client.Generate(context.Background(), testReq())
	require.NoError(t, err)
	assert.Equal(t, "Hello!", resp.Content)
	assert.Greater(t, resp.CostUSD, 0.0)
	assert.Equal(t, 1, primary.calls)

	span := rec.span(t, "chat gpt-4.1")
	assert.Equal(t, trace.SpanKindClient, span.SpanKind)
	assert.Equal(t, "chat", requireAttr(t, span, "gen_ai.operation.name").AsString())
	assert.Equal(t, "openai", requireAttr(t, span, "gen_ai.provider.name").AsString())
	assert.Equal(t, "gpt-4.1", requireAttr(t, span, "gen_ai.request.model").AsString())
	assert.Equal(t, "api.openai.com", requireAttr(t, span, "server.address").AsString())
	assert.Equal(t, int64(443), requireAttr(t, span, "server.port").AsInt64())
	assert.Equal(t, "gpt-4.1", requireAttr(t, span, "gen_ai.response.model").AsString())
	assert.Equal(t, "chatcmpl_test", requireAttr(t, span, "gen_ai.response.id").AsString())
	assert.Equal(t, []string{"stop"}, requireAttr(t, span, "gen_ai.response.finish_reasons").AsStringSlice())
	assert.Equal(t, int64(10), requireAttr(t, span, "gen_ai.usage.input_tokens").AsInt64())
	assert.Equal(t, int64(5), requireAttr(t, span, "gen_ai.usage.output_tokens").AsInt64())
	assert.Equal(t, resp.CostUSD, requireAttr(t, span, "base14.gen_ai.cost_usd").AsFloat64())
	assert.Equal(t, "generate", requireAttr(t, span, "base14.nlsql.stage").AsString())
}

func TestChatSpanUsesGeminiProviderName(t *testing.T) {
	primary := &mockProvider{
		name:    "google",
		address: "generativelanguage.googleapis.com",
		port:    443,
		resp:    &GenerateResponse{Content: "Hi", Model: "gemini-2.5-flash-lite"},
	}
	client, rec := newTestClient(t, primary, nil)

	req := testReq()
	req.Model = "gemini-2.5-flash-lite"
	_, err := client.Generate(context.Background(), req)
	require.NoError(t, err)

	span := rec.span(t, "chat gemini-2.5-flash-lite")
	assert.Equal(t, "gcp.gemini", requireAttr(t, span, "gen_ai.provider.name").AsString())
}

func TestContentCaptureGate(t *testing.T) {
	run := func(capture bool) *recorded {
		client, rec := newTestClient(t, openAIMock(), nil)
		client.CaptureContent = capture
		_, err := client.Generate(context.Background(), testReq())
		require.NoError(t, err)
		return rec
	}

	t.Run("off omits the inference event", func(t *testing.T) {
		span := run(false).span(t, "chat gpt-4.1")
		assert.Empty(t, span.Events, "no event is recorded when capture is off")
	})

	t.Run("on records one inference event", func(t *testing.T) {
		span := run(true).span(t, "chat gpt-4.1")
		require.Len(t, span.Events, 1)
		event := span.Events[0]
		assert.Equal(t, "gen_ai.client.inference.operation.details", event.Name)

		attrs := map[string]string{}
		for _, kv := range event.Attributes {
			attrs[string(kv.Key)] = kv.Value.AsString()
		}
		assert.Equal(t, "Say hello", attrs["gen_ai.input.messages"])
		assert.Equal(t, "You are a test assistant.", attrs["gen_ai.system_instructions"])
		assert.Equal(t, "Hello!", attrs["gen_ai.output.messages"])
	})
}

func TestContentEventOmitsEmptySystemInstructions(t *testing.T) {
	client, rec := newTestClient(t, openAIMock(), nil)
	client.CaptureContent = true

	req := testReq()
	req.System = ""
	_, err := client.Generate(context.Background(), req)
	require.NoError(t, err)

	span := rec.span(t, "chat gpt-4.1")
	require.Len(t, span.Events, 1)
	for _, kv := range span.Events[0].Attributes {
		assert.NotEqual(t, "gen_ai.system_instructions", string(kv.Key))
	}
}

func TestContentEventScrubsPII(t *testing.T) {
	primary := openAIMock()
	primary.resp.Content = "Contact ops@example.com or call 415-555-0100"
	client, rec := newTestClient(t, primary, nil)
	client.CaptureContent = true

	req := testReq()
	req.Prompt = "My card is 4111 1111 1111 1111"
	_, err := client.Generate(context.Background(), req)
	require.NoError(t, err)

	span := rec.span(t, "chat gpt-4.1")
	require.Len(t, span.Events, 1)
	attrs := map[string]string{}
	for _, kv := range span.Events[0].Attributes {
		attrs[string(kv.Key)] = kv.Value.AsString()
	}
	assert.Equal(t, "My card is [CARD]", attrs["gen_ai.input.messages"])
	assert.Equal(t, "Contact [EMAIL] or call [PHONE]", attrs["gen_ai.output.messages"])
}

func TestFailedChatRecordsErrorOnSpan(t *testing.T) {
	primary := &mockProvider{
		name:    "openai",
		address: "api.openai.com",
		port:    443,
		failN:   10,
		failErr: errors.New("503 service unavailable"),
	}
	client, rec := newTestClient(t, primary, nil)

	_, err := client.Generate(context.Background(), testReq())
	require.Error(t, err)

	span := rec.span(t, "chat gpt-4.1")
	assert.Equal(t, codes.Error, span.Status.Code)
	assert.Equal(t, "server_error", requireAttr(t, span, "error.type").AsString())
	require.Len(t, span.Events, 1)
	assert.Equal(t, "exception", span.Events[0].Name)
}

func TestRetrySucceedsWithinOneSpan(t *testing.T) {
	primary := openAIMock()
	primary.failN = 2
	primary.failErr = errors.New("rate limit")
	client, rec := newTestClient(t, primary, nil)

	resp, err := client.Generate(context.Background(), testReq())
	require.NoError(t, err)
	assert.Equal(t, "Hello!", resp.Content)
	assert.Equal(t, 3, primary.calls)

	span := rec.span(t, "chat gpt-4.1")
	assert.NotEqual(t, codes.Error, span.Status.Code, "a retried call that succeeds is not an error")
}

func TestRetryStopsAfterThreeAttempts(t *testing.T) {
	primary := &mockProvider{
		name:    "openai",
		failN:   10,
		failErr: errors.New("always fails"),
	}
	client, _ := newTestClient(t, primary, nil)

	_, err := client.Generate(context.Background(), testReq())
	assert.Error(t, err)
	assert.Equal(t, 3, primary.calls)
}

func TestFallbackSwitchesProviderAndModel(t *testing.T) {
	primary := &mockProvider{
		name:    "openai",
		failN:   10,
		failErr: errors.New("primary down"),
	}
	fallback := &mockProvider{
		name:    "anthropic",
		address: "api.anthropic.com",
		port:    443,
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
	assert.Equal(t, "claude-haiku-4-5-20251001", fallback.lastModel)
}

func TestFallbackToTheSameProviderIsSkipped(t *testing.T) {
	primary := &mockProvider{name: "ollama", failN: 10, failErr: errors.New("primary down")}
	fallback := &mockProvider{name: "ollama", resp: &GenerateResponse{Content: "never used"}}
	client, _ := newTestClient(t, primary, fallback)

	_, err := client.Generate(context.Background(), testReq())
	require.Error(t, err)
	assert.Equal(t, 0, fallback.calls, "switching to the same provider is not a fallback")
}

func TestGenerateWithoutFallbackReturnsError(t *testing.T) {
	primary := &mockProvider{name: "openai", failN: 10, failErr: errors.New("always fails")}
	client, _ := newTestClient(t, primary, nil)

	_, err := client.Generate(context.Background(), testReq())
	require.Error(t, err)
	assert.Contains(t, err.Error(), "failed after 3 attempts")
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
		{"context canceled", errors.New("provider ollama failed after 3 attempts: context canceled"), "canceled"},
		{"unknown error", errors.New("something unexpected"), "unknown_error"},
		{"nil error", nil, "unknown_error"},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			assert.Equal(t, tt.expected, classifyError(tt.err))
		})
	}
}
