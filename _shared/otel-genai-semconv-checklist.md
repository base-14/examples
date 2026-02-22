# OTel GenAI Semantic Conventions Compliance Checklist

Use this checklist when adding or reviewing any AI example in this repo.
Reference: `_shared/llm-gateway-contract.yaml` for the full spec.

---

## Span

- [ ] Span name is `gen_ai.chat {model}` (not `chat {model}` or other variation)
- [ ] `gen_ai.operation.name = "chat"` is set
- [ ] `gen_ai.provider.name` is set (NOT deprecated `gen_ai.system`)
- [ ] `gen_ai.request.model` is set
- [ ] `server.address` is set (use provider-specific address, not localhost for cloud providers)
- [ ] `server.port` is set (443 for cloud providers, 11434 for Ollama)
- [ ] `gen_ai.request.temperature` is set
- [ ] `gen_ai.request.max_tokens` is set
- [ ] `gen_ai.response.model` is set from actual response (may differ from request model)
- [ ] `gen_ai.response.id` is set if provider returns one
- [ ] `gen_ai.response.finish_reasons` is set as an array
- [ ] `gen_ai.usage.input_tokens` is set
- [ ] `gen_ai.usage.output_tokens` is set
- [ ] `gen_ai.usage.cost_usd` is set (calculated from `_shared/pricing.json`)
- [ ] `error.type` is set on exceptions (use exception class name)

## Span Events

- [ ] `gen_ai.user.message` event is emitted (not `gen_ai.client.inference.operation.details`)
- [ ] `gen_ai.assistant.message` event is emitted
- [ ] Events are gated on `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true`
- [ ] Prompt/completion content is PII-scrubbed before recording
- [ ] Prompt (`gen_ai.prompt`) is truncated at 1000 chars
- [ ] System instructions (`gen_ai.system_instructions`) are truncated at 500 chars
- [ ] Completion (`gen_ai.completion`) is truncated at 2000 chars
- [ ] `gen_ai.system_instructions` is omitted if system prompt is empty/absent

## Metrics (all 6 required)

- [ ] `gen_ai.client.token.usage` histogram — input and output recorded separately with `gen_ai.token.type`
- [ ] `gen_ai.client.operation.duration` histogram — wall-clock seconds
- [ ] `gen_ai.client.cost` counter — USD from `_shared/pricing.json`
- [ ] `gen_ai.client.retry.count` counter — incremented before each retry
- [ ] `gen_ai.client.fallback.count` counter — incremented when fallback triggers
- [ ] `gen_ai.client.error.count` counter — incremented on each unhandled exception

## Error Resilience

- [ ] Retry catches ALL exceptions (not network-only)
- [ ] Max 3 attempts total (2 retries after initial)
- [ ] Exponential backoff: multiplier=1, min=1s, max=10s
- [ ] Fallback switches to secondary provider on all failures after retries exhausted
- [ ] `gen_ai.client.fallback.count` metric recorded when fallback triggers
- [ ] Fallback provider/model configurable via env vars

## Configuration

- [ ] Provider selectable via env var (not hardcoded)
- [ ] Fallback provider selectable via env var
- [ ] All API keys come from env vars
- [ ] Ollama base URL configurable via `OLLAMA_BASE_URL`
- [ ] Pricing loaded from `_shared/pricing.json` (not inline dict)

## Tests

- [ ] Cost calculation tested for at least one known model
- [ ] Fallback logic tested with mocked primary failure
- [ ] Retry tested with mocked transient failure
- [ ] Span events tested with `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true`
- [ ] `server.port` is 11434 for Ollama (not 443)

## Anti-Patterns to Avoid

- ❌ `gen_ai.system` attribute (deprecated, use `gen_ai.provider.name`)
- ❌ `gen_ai.client.inference.operation.details` event (replaced by user/assistant events)
- ❌ Hardcoded `server.port = 443` for Ollama
- ❌ `token_count or 0` (fails for legitimate zero-token responses — use `is not None`)
- ❌ Pricing inline in source code (use `_shared/pricing.json`)
- ❌ Retry only on network exceptions (retry ALL exceptions)
