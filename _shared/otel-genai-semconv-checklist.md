# OTel GenAI Semantic Conventions Compliance Checklist

Use this checklist when adding or reviewing any AI example in this repo.
Reference: `_shared/llm-gateway-contract.yaml` for the full spec. Source:
open-telemetry/semantic-conventions-genai (repo, checked 2026-09-15). The repo
has no tagged release, so it is cited by repo and date, not by version.

Naming rule: application-specific attributes and metrics must not sit under an
existing semconv namespace (`gen_ai.*`, `mcp.*`, and so on). Custom names use a
`base14.` prefix. Shipped examples keep their current attribute and metric
names until each is next touched.

---

## Span

- [ ] Span name is `chat {model}` (not `gen_ai.chat {model}` or other variation).
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
- [ ] `base14.gen_ai.cost_usd` is set (calculated from `_shared/pricing.json`)
- [ ] `error.type` is set on exceptions (use exception class name)

## Span Events

- [ ] `gen_ai.client.inference.operation.details` event is emitted (not the removed
  `gen_ai.user.message` / `gen_ai.assistant.message` events).
- [ ] Event is gated on `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true`.
- [ ] Prompt/completion content is PII-scrubbed before recording.
- [ ] Prompt (`gen_ai.input.messages`) is truncated at 1000 chars.
- [ ] System instructions (`gen_ai.system_instructions`) are truncated at 500 chars.
- [ ] Completion (`gen_ai.output.messages`) is truncated at 2000 chars.
- [ ] `gen_ai.system_instructions` is omitted if system prompt is empty/absent.

## Metrics (all 6 required)

- [ ] `gen_ai.client.token.usage` histogram, input and output recorded separately with `gen_ai.token.type`.
- [ ] `gen_ai.client.operation.duration` histogram, wall-clock seconds.
- [ ] `base14.gen_ai.cost` counter, USD from `_shared/pricing.json`.
- [ ] `base14.gen_ai.retry.count` counter, incremented before each retry.
- [ ] `base14.gen_ai.fallback.count` counter, incremented when fallback triggers.
- [ ] `base14.gen_ai.error.count` counter, incremented on each unhandled exception.

## Agent Metrics (when the example has an agent loop)

- [ ] `gen_ai.invoke_agent.duration` histogram, end-to-end duration of one agent invocation.
- [ ] `gen_ai.invoke_agent.inference_calls` histogram, model calls issued by that invocation.
- [ ] `gen_ai.invoke_agent.tool_calls` histogram, tool calls issued by that invocation.

## MCP (when the example uses Model Context Protocol)

- [ ] Client span name is `{mcp.method.name} {target}`, target is the tool or prompt name when known.
- [ ] Server span name follows the same format.
- [ ] `mcp.method.name` is set (required).
- [ ] `mcp.session.id` is set when the call is part of a session.
- [ ] `mcp.protocol.version` is set.
- [ ] `mcp.resource.uri` is set on resource-related requests, opt-in on the client metric.
- [ ] `gen_ai.tool.name` is set when the call is a tool call.
- [ ] The client injects W3C `traceparent` (and `tracestate`, `baggage` if used) into the MCP request's
  `params._meta`, with the context propagation keys left unprefixed even though `params._meta` keys are
  otherwise DNS-prefixed by MCP convention.
- [ ] The server uses the context extracted from `params._meta` as the parent of the server span, and links
  the current ambient context (the `_meta` parenting rule).
- [ ] If the MCP instrumentation can reliably detect that an outer GenAI `execute_tool` span already covers the
  call, it does not create a separate MCP client span, and instead adds MCP-specific attributes to that outer
  span. When the instrumentation cannot detect this, or does not support it, both spans appear, and the example
  says so rather than treating it as a bug.
- [ ] `mcp.client.operation.duration` and `mcp.server.operation.duration` are recorded, and the same tool call
  is not also counted in `gen_ai.execute_tool.duration` from the agent framework, to avoid double-counting.

## Approval Waits (when a tool call pauses for a human decision)

An approval wait is recorded as two short linked spans and a pair of metrics, not as one span held
open for the length of the wait. A span that outlives its parent request breaks tail sampling
decision windows and distorts request-duration views, so neither span stays open past its own
request.

- [ ] `base14.approval.requested {tool}` is created inside the run's trace when the app decides a
  call needs a human decision, and ends at once.
- [ ] `base14.approval.decided {tool}` is created when the decision is made (approval, rejection, or
  timeout), links to the requested span, and ends at once.
- [ ] Both spans carry `gen_ai.tool.name`, `base14.approval.amount`, and `base14.approval.limit`.
- [ ] `base14.approval.decided` carries `base14.approval.outcome`, one of `approved`, `rejected`, or
  `expired`, and `base14.approval.wait_seconds`.
- [ ] Auto-approved calls get no spans. The counter below additionally carries outcome `auto` for them,
  a value the spans never carry.
- [ ] `base14.agent.approval.wait.duration` histogram, unit seconds, records the wait between request
  and decision, by tool and outcome.
- [ ] `base14.agent.approval.count` counter records every decision, by tool and outcome, including
  auto-approved calls with outcome `auto`.

## Error Resilience

- [ ] Retry catches ALL exceptions (not network-only)
- [ ] Max 3 attempts total (2 retries after initial)
- [ ] Exponential backoff: multiplier=1, min=1s, max=10s
- [ ] Fallback switches to secondary provider on all failures after retries exhausted
- [ ] `base14.gen_ai.fallback.count` metric recorded when fallback triggers.
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
- ❌ Hardcoded `server.port = 443` for Ollama
- ❌ `token_count or 0` (fails for legitimate zero-token responses — use `is not None`)
- ❌ Pricing inline in source code (use `_shared/pricing.json`)
- ❌ Retry only on network exceptions (retry ALL exceptions)
- ❌ A custom attribute or metric name placed under `gen_ai.*`, `mcp.*`, or another existing semconv
  namespace (use the `base14.` prefix).
- ❌ One approval span held open for the length of the wait (use the linked requested/decided pair).
