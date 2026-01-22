# AI Sales Intelligence

AI-powered sales intelligence agent demonstrating **unified observability** for AI applications using OpenTelemetry and Base14 Scout.

## Why Unified Observability?

Modern AI applications combine traditional infrastructure (HTTP, databases) with AI/LLM operations. Most teams use **fragmented tools**:

```
Fragmented Observability (The Problem)
┌─────────────────────────────────────────────────────────────────┐
│  Datadog/New Relic     LangSmith/W&B        Custom Dashboards   │
│  ┌─────────────┐      ┌─────────────┐      ┌─────────────┐     │
│  │ HTTP/DB     │      │ LLM Traces  │      │ Agent       │     │
│  │ Metrics     │      │ Prompt Logs │      │ Metrics     │     │
│  └─────────────┘      └─────────────┘      └─────────────┘     │
│        │                    │                    │              │
│        └──────────── NO CORRELATION ─────────────┘              │
│                                                                  │
│  ❌ Can't trace: User request → Agent → LLM call → DB query     │
│  ❌ Can't answer: "Which LLM call caused this slow API response?"│
│  ❌ Can't correlate: Token costs with business transactions      │
└─────────────────────────────────────────────────────────────────┘
```

This project demonstrates **unified observability** where a single trace spans the entire request:

```
Unified Observability (The Solution)
┌─────────────────────────────────────────────────────────────────┐
│  POST /campaigns/{id}/run                              8.42s    │
│  │                                                              │
│  ├─● db.query SELECT connections                       12ms     │
│  ├─▼ invoke_agent research                             0.18s    │
│  │  └─● db.query SELECT (FTS)                          15ms     │
│  ├─▼ invoke_agent enrich                               2.14s    │
│  │  └─● gen_ai.chat claude-sonnet-4 (1240 tokens)      0.89s    │
│  ├─▼ invoke_agent score                                1.82s    │
│  │  └─● gen_ai.chat claude-opus-4 (2550 tokens)        1.82s    │
│  ├─▼ invoke_agent draft                                3.21s    │
│  │  └─● gen_ai.chat claude-sonnet-4 (5390 tokens)      3.21s    │
│  ├─▼ invoke_agent evaluate                             1.07s    │
│  │  ├─● gen_ai.chat claude-sonnet-4 (1200 tokens)      0.98s    │
│  │  └─◆ gen_ai.evaluation.result: score=87, passed              │
│  └─● db.query INSERT prospects                         8ms      │
│                                                                  │
│  ✅ Full correlation: HTTP → Agent → LLM → DB                   │
│  ✅ Cost attribution: $0.042 for this request                   │
│  ✅ Performance insight: draft agent is the bottleneck          │
└─────────────────────────────────────────────────────────────────┘
```

## Stack Profile

| Component | Technology | Version |
|-----------|------------|---------|
| Runtime | Python | 3.14 |
| Web Framework | FastAPI | 0.128+ |
| Agent Framework | LangGraph | 1.0.6+ |
| LLM Providers | Anthropic, Google, OpenAI | Latest |
| Database | PostgreSQL | 18 |
| Observability | OpenTelemetry SDK | 1.39+ |
| Observability Backend | Base14 Scout | - |

## What's Instrumented

| Layer | Method | What You Get |
|-------|--------|--------------|
| **HTTP Requests** | Auto (`FastAPIInstrumentor`) | Request spans with method, path, status, duration |
| **Database Queries** | Auto (`SQLAlchemyInstrumentor`) | Query spans with SQL, parameters, duration |
| **External HTTP** | Auto (`HTTPXClientInstrumentor`) | Outbound call spans (LLM API requests) |
| **Logging** | Auto (`LoggingInstrumentor`) | Trace-correlated log records |
| **LLM Calls** | Custom (`llm.py`) | GenAI semantic attributes, token/cost metrics |
| **Agent Pipeline** | Custom (`graph.py`) | `invoke_agent {name}` spans with business context |
| **Evaluations** | Custom (`evaluate.py`) | `gen_ai.evaluation.result` events |

### Auto vs Custom Instrumentation

**Auto-instrumentation** (zero code changes):
- Handled by OpenTelemetry instrumentors
- Captures HTTP, DB, external calls automatically
- Great for infrastructure visibility

**Custom instrumentation** (in this project):
- Required because auto-instrumentation doesn't understand LLM semantics
- Adds GenAI-specific attributes (model, tokens, cost, provider)
- Enables business context (agent name, campaign ID for attribution)
- Records GenAI metrics for dashboards and alerts

## Quick Start

### Prerequisites

- Python 3.14+
- Docker & Docker Compose
- API keys for at least one LLM provider

### Setup

```bash
# Clone and navigate
cd examples/python/ai-sales-intelligence

# Install dependencies
make dev

# Copy and configure environment
cp .env.example .env
# Edit .env with your API keys

# Start PostgreSQL and OTel Collector
docker compose up -d

# Run the application
make run
```

### Test the API

```bash
# Run the test script
./scripts/test-api.sh

# Or manually:
# 1. Health check
curl http://localhost:8000/health

# 2. Create a campaign
curl -X POST http://localhost:8000/campaigns \
  -H "Content-Type: application/json" \
  -d '{"name": "Test", "target_keywords": ["AI"], "target_titles": ["CTO"]}'

# 3. Import connections
curl -X POST http://localhost:8000/connections/import \
  -F "file=@data/sample-connections.csv"

# 4. Run the pipeline (generates LLM traces)
curl -X POST http://localhost:8000/campaigns/{id}/run \
  -H "Content-Type: application/json" \
  -d '{"score_threshold": 50, "quality_threshold": 60}'
```

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `LLM_PROVIDER` | Primary LLM provider (`anthropic`, `google`, `openai`) | `anthropic` |
| `LLM_MODEL` | Primary model name | `claude-sonnet-4-20250514` |
| `FALLBACK_PROVIDER` | Fallback provider on errors | `google` |
| `FALLBACK_MODEL` | Fallback model name | `gemini-3-flash` |
| `ANTHROPIC_API_KEY` | Anthropic API key | - |
| `GOOGLE_API_KEY` | Google AI API key | - |
| `OPENAI_API_KEY` | OpenAI API key | - |
| `DATABASE_URL` | PostgreSQL connection string | `postgresql+asyncpg://...` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | OTel Collector endpoint | `http://localhost:4318` |
| `OTEL_SERVICE_NAME` | Service name in traces | `ai-sales-intelligence` |
| `SCOUT_ENVIRONMENT` | Deployment environment tag | `development` |
| `OTEL_ENABLED` | Enable/disable telemetry | `true` |
| `PROMPTS_CONFIG_PATH` | Custom path to prompts.yaml | `config/prompts.yaml` |

### Supported Models

| Provider | Models | Pricing (per 1M tokens) |
|----------|--------|-------------------------|
| Anthropic | `claude-opus-4-20250514`, `claude-sonnet-4-20250514` | $15/$75, $3/$15 |
| Google | `gemini-3-flash`, `gemini-3-pro-preview` | $0.50/$3, $2/$12 |
| OpenAI | `gpt-4o`, `gpt-4o-mini`, `o1` | $2.50/$10, $0.15/$0.60, $15/$60 |

## Project Structure

```
├── config/
│   └── prompts.yaml     # Externalized prompts & company context
├── src/sales_intelligence/
│   ├── agents/          # LangGraph agent nodes
│   │   ├── research.py  # PostgreSQL FTS search
│   │   ├── enrich.py    # LLM company inference
│   │   ├── score.py     # ICP scoring with LLM
│   │   ├── draft.py     # Email generation
│   │   └── evaluate.py  # Quality evaluation ⭐
│   ├── middleware/
│   │   └── metrics.py   # HTTP request metrics ⭐
│   ├── config.py        # Pydantic settings
│   ├── database.py      # Async SQLAlchemy
│   ├── models.py        # ORM models
│   ├── state.py         # Pydantic agent state
│   ├── graph.py         # LangGraph pipeline ⭐
│   ├── llm.py           # LLM client with observability ⭐
│   ├── prompts.py       # Prompt loader from YAML
│   ├── telemetry.py     # OpenTelemetry setup ⭐
│   └── main.py          # FastAPI app

⭐ = Key observability files
```

## Prompt Customization

All LLM prompts are externalized in `config/prompts.yaml` for easy customization without code changes.

### Company Context

Edit the `company` section to personalize generated emails:

```yaml
# config/prompts.yaml
company:
  name: "Your Company"
  product_name: "Your Product"
  value_proposition: "your unique value proposition"
  sender_name: "Jane Smith"
  sender_title: "Account Executive"
```

These values are automatically interpolated into email drafts:
- `{company_name}` → Your Company
- `{product_name}` → Your Product
- `{value_proposition}` → your unique value proposition
- `{sender_name}` → Jane Smith

### Prompt Templates

Each agent has `system` and `user` prompt templates:

```yaml
prompts:
  draft:
    system: |
      You are an expert B2B sales copywriter for {company_name}.
      Our product: {product_name}
      Our value proposition: {value_proposition}
      ...
    user: |
      Write a personalized cold email for this prospect:
      Name: {first_name} {last_name}
      ...
```

### Custom Config Path

Override the config location via environment variable:

```bash
PROMPTS_CONFIG_PATH=/custom/path/prompts.yaml
```

### Hot Reload (Development)

To reload prompts without restarting:

```python
from sales_intelligence.prompts import reload_config
reload_config()  # Clears cache, next call loads fresh config
```

## OpenTelemetry GenAI Conventions

This project implements the [OpenTelemetry GenAI Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/):

### Span Attributes

```python
# Required
span.set_attribute("gen_ai.operation.name", "chat")
span.set_attribute("gen_ai.provider.name", "anthropic")

# Recommended
span.set_attribute("gen_ai.request.model", "claude-sonnet-4-20250514")
span.set_attribute("gen_ai.usage.input_tokens", 1240)
span.set_attribute("gen_ai.usage.output_tokens", 320)
span.set_attribute("server.address", "api.anthropic.com")
```

### Metrics

| Metric | Type | Description |
|--------|------|-------------|
| `gen_ai.client.token.usage` | Histogram | Tokens per call (input/output) |
| `gen_ai.client.operation.duration` | Histogram | LLM call duration |
| `gen_ai.client.cost` | Counter | Cost in USD |
| `gen_ai.evaluation.score` | Histogram | Quality scores (0-1) |

### Events

```python
# Evaluation results
span.add_event("gen_ai.evaluation.result", {
    "gen_ai.evaluation.name": "email_quality",
    "gen_ai.evaluation.score.value": 87,
    "gen_ai.evaluation.score.label": "passed",
})
```

## Development

```bash
# Run all checks (lint, typecheck, test)
make check

# Run only tests
make test

# Run integration tests (requires Docker)
uv run pytest -m integration

# Format code
make format

# Security audit
make audit
```

## Troubleshooting

### No traces appearing in Scout

1. **Check OTel Collector is running:**
   ```bash
   docker compose ps
   curl http://localhost:4318/v1/traces  # Should return 405
   ```

2. **Check zpages for debugging:**
   ```bash
   # Open http://localhost:55679/debug/tracez
   ```

3. **Verify OTEL_ENABLED is not false:**
   ```bash
   echo $OTEL_ENABLED  # Should be "true" or unset
   ```

### LLM calls failing

1. **Check API key is set:**
   ```bash
   echo $ANTHROPIC_API_KEY  # Should not be empty
   ```

2. **Try fallback provider:**
   ```python
   # Set in .env
   LLM_PROVIDER=google
   LLM_MODEL=gemini-3-flash
   ```

3. **Check rate limits:** The client has automatic retry with exponential backoff (3 attempts).

### Database connection issues

1. **Check PostgreSQL is running:**
   ```bash
   docker compose ps
   docker compose logs postgres
   ```

2. **Check database connectivity:**
   ```bash
   docker compose exec postgres psql -U postgres -c "SELECT 1;"
   ```

### High token costs

1. **Check cost metrics in Scout:**
   ```
   sum(gen_ai.client.cost) by (gen_ai.agent.name)
   ```

2. **Review which agent is expensive:** Usually `draft` or `score` agents use the most tokens.

3. **Consider using cheaper models:**
   ```bash
   # Use Gemini Flash for drafting
   LLM_MODEL=gemini-3-flash
   ```

## References

- [OpenTelemetry GenAI Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/)
- [Base14 Scout Documentation](https://docs.base14.io/)
- [LangGraph Documentation](https://langchain-ai.github.io/langgraph/)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
