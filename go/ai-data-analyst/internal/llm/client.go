package llm

import (
	"context"
	"fmt"
	"strings"
	"time"

	"ai-data-analyst/internal/telemetry"

	"github.com/cenkalti/backoff/v5"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/codes"
	"go.opentelemetry.io/otel/trace"
)

const (
	maxAttempts        = 3
	promptMaxChars     = 1000
	systemMaxChars     = 500
	completionMaxChars = 2000
)

type Client struct {
	Primary       Provider
	Fallback      Provider
	FallbackModel string
	Tracer        trace.Tracer
	Metrics       *telemetry.GenAIMetrics

	// CaptureContent gates the inference details event that carries prompt and
	// completion text. Off by default; OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT
	// turns it on.
	CaptureContent bool

	// Backoff is the retry schedule. Nil means exponential 1 s to 10 s.
	Backoff backoff.BackOff
}

// Generate runs one chat completion against the primary provider and, when
// that fails after its retries, against the fallback provider.
func (c *Client) Generate(ctx context.Context, req GenerateRequest) (*GenerateResponse, error) {
	resp, err := c.chat(ctx, c.Primary, req)
	if err == nil {
		return resp, nil
	}

	if c.Fallback == nil || c.Fallback.Name() == c.Primary.Name() {
		return nil, fmt.Errorf("provider %s failed after %d attempts: %w", c.Primary.Name(), maxAttempts, err)
	}

	c.recordFallback(ctx, err)

	fallbackReq := req
	if c.FallbackModel != "" {
		fallbackReq.Model = c.FallbackModel
	}
	return c.chat(ctx, c.Fallback, fallbackReq)
}

func (c *Client) chat(ctx context.Context, provider Provider, req GenerateRequest) (*GenerateResponse, error) {
	call := telemetry.CallAttrs{
		Provider: SemconvProviderName(provider.Name()),
		Model:    req.Model,
		Stage:    req.Stage,
	}

	spanAttrs := []attribute.KeyValue{
		attribute.String("gen_ai.operation.name", "chat"),
		attribute.String("gen_ai.provider.name", call.Provider),
		attribute.String("gen_ai.request.model", req.Model),
		attribute.String("server.address", provider.ServerAddress()),
		attribute.Int("server.port", provider.ServerPort()),
		attribute.Float64("gen_ai.request.temperature", req.Temperature),
		attribute.Int("gen_ai.request.max_tokens", req.MaxTokens),
	}
	if req.Stage != "" {
		spanAttrs = append(spanAttrs, attribute.String("base14.nlsql.stage", req.Stage))
	}

	ctx, span := c.Tracer.Start(ctx, "chat "+req.Model,
		trace.WithSpanKind(trace.SpanKindClient),
		trace.WithAttributes(spanAttrs...),
	)
	defer span.End()

	start := time.Now()
	resp, err := c.callWithRetry(ctx, provider, req, call)
	duration := time.Since(start).Seconds()

	if err != nil {
		errorType := classifyError(err)
		span.RecordError(err)
		span.SetAttributes(attribute.String("error.type", errorType))
		span.SetStatus(codes.Error, err.Error())
		c.Metrics.RecordError(ctx, call, errorType)
		c.Metrics.RecordDuration(ctx, call, duration, errorType)
		c.emitContentEvent(span, req, nil)
		return nil, err
	}

	resp.CostUSD = CalculateCost(resp.Model, resp.InputTokens, resp.OutputTokens)

	span.SetAttributes(
		attribute.String("gen_ai.response.model", resp.Model),
		attribute.Int("gen_ai.usage.input_tokens", resp.InputTokens),
		attribute.Int("gen_ai.usage.output_tokens", resp.OutputTokens),
		attribute.Float64("base14.gen_ai.cost_usd", resp.CostUSD),
	)
	if resp.ResponseID != "" {
		span.SetAttributes(attribute.String("gen_ai.response.id", resp.ResponseID))
	}
	if resp.FinishReason != "" {
		span.SetAttributes(attribute.StringSlice("gen_ai.response.finish_reasons", []string{resp.FinishReason}))
	}

	c.Metrics.RecordUsage(ctx, call, resp.InputTokens, resp.OutputTokens, resp.CostUSD)
	c.Metrics.RecordDuration(ctx, call, duration, "")
	c.emitContentEvent(span, req, resp)

	return resp, nil
}

func (c *Client) callWithRetry(ctx context.Context, provider Provider, req GenerateRequest, call telemetry.CallAttrs) (*GenerateResponse, error) {
	retries := 0
	return backoff.Retry(ctx,
		func() (*GenerateResponse, error) {
			return provider.Generate(ctx, req)
		},
		backoff.WithBackOff(c.backOff()),
		backoff.WithMaxTries(maxAttempts),
		// Notify runs before each wait, so the attempt that exhausts the
		// budget is not counted as a retry.
		backoff.WithNotify(func(err error, _ time.Duration) {
			retries++
			c.Metrics.RecordRetry(ctx, call, classifyError(err), retries)
		}),
	)
}

func (c *Client) backOff() backoff.BackOff {
	if c.Backoff != nil {
		return c.Backoff
	}
	bo := backoff.NewExponentialBackOff()
	bo.InitialInterval = 1 * time.Second
	bo.MaxInterval = 10 * time.Second
	bo.RandomizationFactor = 0.5
	return bo
}

// recordFallback marks the provider switch on the calling span. The switch is
// a recovery, so the span records the error and an event but keeps its status.
func (c *Client) recordFallback(ctx context.Context, err error) {
	errorType := classifyError(err)
	from := SemconvProviderName(c.Primary.Name())
	to := SemconvProviderName(c.Fallback.Name())

	span := trace.SpanFromContext(ctx)
	span.RecordError(err)
	span.AddEvent("provider_fallback", trace.WithAttributes(
		attribute.String("gen_ai.provider.name", from),
		attribute.String("base14.gen_ai.fallback.provider", to),
		attribute.String("error.type", errorType),
	))
	span.SetAttributes(attribute.Bool("gen_ai.fallback.triggered", true))

	c.Metrics.RecordFallback(ctx, from, to, errorType)
}

func (c *Client) emitContentEvent(span trace.Span, req GenerateRequest, resp *GenerateResponse) {
	if !c.CaptureContent {
		return
	}

	attrs := []attribute.KeyValue{
		attribute.String("gen_ai.input.messages", scrubAndTruncate(req.Prompt, promptMaxChars)),
	}
	if system := scrubAndTruncate(req.System, systemMaxChars); system != "" {
		attrs = append(attrs, attribute.String("gen_ai.system_instructions", system))
	}
	if resp != nil {
		attrs = append(attrs, attribute.String("gen_ai.output.messages", scrubAndTruncate(resp.Content, completionMaxChars)))
	}

	span.AddEvent("gen_ai.client.inference.operation.details", trace.WithAttributes(attrs...))
}

func classifyError(err error) string {
	if err == nil {
		return "unknown_error"
	}
	msg := strings.ToLower(err.Error())
	switch {
	case strings.Contains(msg, "rate limit") || strings.Contains(msg, "429"):
		return "rate_limit"
	case strings.Contains(msg, "canceled"):
		return "canceled"
	case strings.Contains(msg, "timeout") || strings.Contains(msg, "deadline"):
		return "timeout"
	case strings.Contains(msg, "401") || strings.Contains(msg, "403") || strings.Contains(msg, "auth") || strings.Contains(msg, "api key"):
		return "auth_error"
	case strings.Contains(msg, "400") || strings.Contains(msg, "422") || strings.Contains(msg, "invalid"):
		return "invalid_request"
	case strings.Contains(msg, "500") || strings.Contains(msg, "502") || strings.Contains(msg, "503") || strings.Contains(msg, "server"):
		return "server_error"
	case strings.Contains(msg, "connect") || strings.Contains(msg, "dns") || strings.Contains(msg, "network") || strings.Contains(msg, "reset"):
		return "network_error"
	default:
		return "unknown_error"
	}
}
