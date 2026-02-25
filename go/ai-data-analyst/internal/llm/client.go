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

type GenerateRequest struct {
	Model       string
	System      string
	Prompt      string
	Temperature float64
	MaxTokens   int
	Stage       string
}

type GenerateResponse struct {
	Content      string
	Model        string
	InputTokens  int
	OutputTokens int
	CostUSD      float64
	FinishReason string
}

type Provider interface {
	Generate(ctx context.Context, req GenerateRequest) (*GenerateResponse, error)
	Name() string
}

type Client struct {
	Primary              Provider
	Fallback             Provider
	Tracer               trace.Tracer
	Metrics              *telemetry.GenAIMetrics
	PrimaryProvider      string
	FallbackProviderName string
	FallbackModel        string
}

func (c *Client) GenerateOnce(ctx context.Context, provider Provider, providerName string, req GenerateRequest) (*GenerateResponse, error) {
	spanName := "gen_ai.chat " + req.Model
	start := time.Now()

	ctx, span := c.Tracer.Start(ctx, spanName)
	defer span.End()

	serverAddr := ProviderServers[providerName]
	serverPort := ProviderPorts[providerName]

	span.SetAttributes(
		attribute.String("gen_ai.operation.name", "chat"),
		attribute.String("gen_ai.provider.name", providerName),
		attribute.String("gen_ai.request.model", req.Model),
		attribute.String("server.address", serverAddr),
		attribute.Int("server.port", serverPort),
		attribute.Float64("gen_ai.request.temperature", req.Temperature),
		attribute.Int("gen_ai.request.max_tokens", req.MaxTokens),
	)

	if req.Stage != "" {
		span.SetAttributes(attribute.String("nlsql.stage", req.Stage))
	}

	span.AddEvent("gen_ai.user.message", trace.WithAttributes(
		attribute.String("gen_ai.prompt", truncate(req.Prompt, 1000)),
	))
	if req.System != "" {
		span.AddEvent("gen_ai.user.message", trace.WithAttributes(
			attribute.String("gen_ai.system_instructions", truncate(req.System, 500)),
		))
	}

	resp, err := provider.Generate(ctx, req)
	duration := time.Since(start).Seconds()

	if err != nil {
		span.SetStatus(codes.Error, err.Error())
		span.SetAttributes(attribute.String("error.type", classifyError(err)))
		if c.Metrics != nil {
			c.Metrics.ErrorCount.Add(ctx, 1,
				telemetry.WithProviderModel(providerName, req.Model),
			)
		}
		return nil, err
	}

	resp.CostUSD = CalculateCost(resp.Model, resp.InputTokens, resp.OutputTokens)

	span.SetAttributes(
		attribute.String("gen_ai.response.model", resp.Model),
		attribute.Int("gen_ai.usage.input_tokens", resp.InputTokens),
		attribute.Int("gen_ai.usage.output_tokens", resp.OutputTokens),
		attribute.Float64("gen_ai.usage.cost_usd", resp.CostUSD),
	)
	if resp.FinishReason != "" {
		span.SetAttributes(attribute.String("gen_ai.response.finish_reasons", resp.FinishReason))
	}

	span.AddEvent("gen_ai.assistant.message", trace.WithAttributes(
		attribute.String("gen_ai.completion", truncate(resp.Content, 2000)),
	))

	if c.Metrics != nil {
		c.Metrics.RecordGenAIMetrics(ctx, telemetry.RecordParams{
			Provider:     providerName,
			Model:        resp.Model,
			Stage:        req.Stage,
			InputTokens:  resp.InputTokens,
			OutputTokens: resp.OutputTokens,
			DurationSec:  duration,
			CostUSD:      resp.CostUSD,
		})
	}

	return resp, nil
}

func (c *Client) GenerateWithRetry(ctx context.Context, provider Provider, providerName string, req GenerateRequest) (*GenerateResponse, error) {
	var retries int
	bo := backoff.NewExponentialBackOff()
	bo.InitialInterval = 1 * time.Second
	bo.MaxInterval = 10 * time.Second
	bo.RandomizationFactor = 0.5 // symmetric ±50%: interval randomly in [0.5*base, 1.5*base]

	resp, err := backoff.Retry(ctx, func() (*GenerateResponse, error) {
		resp, err := c.GenerateOnce(ctx, provider, providerName, req)
		if err != nil {
			retries++
			if c.Metrics != nil {
				c.Metrics.RetryCount.Add(ctx, 1,
					telemetry.WithProviderModel(providerName, req.Model),
				)
			}
			return nil, err
		}
		return resp, nil
	},
		backoff.WithBackOff(bo),
		backoff.WithMaxTries(3),
	)

	return resp, err
}

func (c *Client) Generate(ctx context.Context, req GenerateRequest) (*GenerateResponse, error) {
	resp, err := c.GenerateWithRetry(ctx, c.Primary, c.PrimaryProvider, req)
	if err == nil {
		return resp, nil
	}

	if c.Fallback == nil {
		return nil, fmt.Errorf("primary provider %s failed after retries: %w", c.PrimaryProvider, err)
	}

	if c.Metrics != nil {
		c.Metrics.FallbackCount.Add(ctx, 1)
	}

	fallbackReq := req
	if c.FallbackModel != "" {
		fallbackReq.Model = c.FallbackModel
	}
	return c.GenerateWithRetry(ctx, c.Fallback, c.FallbackProviderName, fallbackReq)
}

func classifyError(err error) string {
	if err == nil {
		return "unknown_error"
	}
	msg := strings.ToLower(err.Error())
	switch {
	case strings.Contains(msg, "rate limit") || strings.Contains(msg, "429"):
		return "rate_limit"
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

func truncate(s string, max int) string {
	if len(s) <= max {
		return s
	}
	return s[:max]
}
