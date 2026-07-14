# AI Runbook Assistant - Dashboard Design Specification

This document describes the conceptual design for the observability dashboards shipped with the AI Runbook Assistant.
The designs are implementation-agnostic and can be adapted to any visualization platform (Grafana, Datadog, Scout,
custom).

The application is a single SRE runbook agent: per request it invokes a RAG retriever over the runbook corpus, calls SRE
tools (`search_runbooks`, `query_metrics`, `search_logs`, `get_service_status`), then synthesizes a diagnosis. It emits
OpenTelemetry GenAI-semconv telemetry through a custom LangChain callback handler. Two dashboards ship with it: an
**Operational** view for live request health and a **Strategic** view for cost, volume, and efficiency trends.

The span tree for one request looks like this:

```plain
invoke_agent runbook_assistant
├─ retrieval runbooks            (RAG over the runbook corpus)
├─ chat {model}                  (reasoning / tool selection)
├─ execute_tool {tool}           (search_runbooks | query_metrics | search_logs | get_service_status)
├─ chat {model}                  (synthesis)
└─ ...                           (+ SQLAlchemy and FastAPI HTTP spans)
```

---

## Dashboard 1: Operational

**Purpose**: Monitor live request health - latency, tokens, errors, tool activity, and retrieval quality.

### Operational Layout

```plain
┌─────────────────────────────────────────────────────────────────────────────┐
│ HEADER: AI Runbook Assistant — Operational               [Time Range] [Refresh]│
├─────────────────────────────────────────────────────────────────────────────┤
│ FILTERS: [Service ▼] [Model ▼] [Agent ▼] [Provider ▼]                       │
├────────────┬────────────┬────────────┬────────────────────────────────────┤
│  Total     │  Input     │  Output    │  Output / Input %                    │
│  Tokens    │  Tokens    │  Tokens    │  ██%                                 │
├────────────┴────────────┴────────────┴────────────────────────────────────┤
│ ROW: Token Usage                                                            │
│  DONUT Tokens by Model │ DONUT Tokens by Provider │ TS Input vs Output      │
├────────────────────────────────────────────────────────────────────────────┤
│ ROW: Cost Attribution                                                       │
│  Total Cost │ Avg Cost/Req │ Daily Run Rate │ Cost per 1K Tokens            │
│  DONUT Cost by Model │ DONUT Cost by Provider │ TS Cost Rate by Provider     │
├────────────────────────────────────────────────────────────────────────────┤
│ ROW: Tool & Retrieval Activity                                              │
│  Tool Calls │ Tool Failures │ Retrieval Calls │ Avg Chunks │ RAG Degraded   │
│  TS Tool Calls by Tool │ TS Avg Chunks Retrieved                            │
├────────────────────────────────────────────────────────────────────────────┤
│ ROW: Request Performance                                                    │
│  Total Requests │ Avg Duration │ p99 Duration │ Success Rate (gauge)        │
│  TS Tool Latency by Tool │ TS Error Rate │ TABLE Tool Performance Summary   │
├────────────────────────────────────────────────────────────────────────────┤
│ ROW: Error Analysis                                                         │
│  Total Errors │ DONUT Errors by Type │ BAR Errors by Provider │ TS Errors   │
├────────────────────────────────────────────────────────────────────────────┤
│ ROW: Database Impact                                                        │
│  DB Avg Latency │ DB Queries/Req │ DB p99 │ DB Error Count                  │
│  TS DB Latency vs Request Duration │ TS DB Query Duration by Operation      │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Operational Panel Specifications

| Panel | Type | Data Source | Purpose |
|-------|------|-------------|---------|
| Total / Input / Output Tokens | Stat | `gen_ai.client.token.usage` (split by `gen_ai.token.type`) | Token consumption at a glance |
| Output / Input % | Stat | Calculated from token usage | Prompt-vs-completion efficiency |
| Tokens by Model | Donut | Group by `gen_ai.request.model` | Model usage distribution |
| Tokens by Provider | Donut | Group by `gen_ai.provider.name` | Provider distribution |
| Input vs Output Over Time | Time Series | Split by `gen_ai.token.type` | Usage pattern over time |
| Total Cost | Stat | `gen_ai.client.cost` increase | Period spend (zero on local Ollama) |
| Avg Cost / Request | Stat | cost / `invoke_agent` span count | Unit economics |
| Daily Run Rate | Stat | cost rate * 86400 | Spend projection |
| Cost per 1K Tokens | Stat | cost / tokens * 1000 | Token-cost efficiency |
| Cost by Model / Provider | Donut | Group by model / provider | Spend attribution |
| Cost Rate by Provider | Time Series | `gen_ai.client.cost` increase per provider | Spend trend |
| Tool Calls | Stat | `execute_tool` span count | Tool activity volume |
| Tool Failures | Stat | `tool_execution_failed` span events | Tool reliability |
| Retrieval Calls | Stat | `retrieval` span count | RAG activity volume |
| Avg Chunks Retrieved | Stat | avg `app.retrieval.chunk_count` | RAG recall depth |
| RAG Degraded | Stat | `rag_retrieval_degraded` span events | Retriever fallbacks |
| Tool Calls by Tool | Time Series | Group `execute_tool` by `gen_ai.tool.name` | Tool mix over time |
| Avg Chunks Retrieved Over Time | Time Series | avg `app.retrieval.chunk_count` | Retrieval depth trend |
| Total Requests | Stat | `invoke_agent` span count | Request volume |
| Avg / p99 Duration | Stat | `invoke_agent` span `Duration` | Per-request latency |
| Success Rate | Gauge | (total - errors) / total on `invoke_agent` | Reliability |
| Tool Latency by Tool | Time Series | avg `execute_tool` `Duration` by `gen_ai.tool.name` | Slow-tool detection |
| Error Rate Over Time | Time Series | error spans / total `invoke_agent` | Error trend |
| Tool Performance Summary | Table | per `gen_ai.tool.name`: calls, p50/p90/p99, errors | Tool drill-down |
| Total Errors | Stat | `gen_ai.client.error.count` increase | Error volume |
| Errors by Type | Donut | Group by `error.type` | Error classification |
| Errors by Provider | Bar | Group by `gen_ai.provider.name` | Provider error attribution |
| Errors Over Time by Type | Time Series | count by `error.type` | Error pattern timing |
| DB Avg / p99 Latency | Stat | SQLAlchemy spans, `db.system=postgresql` | Database health |
| DB Queries / Request | Stat | DB spans / `invoke_agent` count | Query fan-out |
| DB Error Count | Stat | errored DB spans | Database reliability |
| DB Latency vs Request Duration | Time Series | DB avg vs `invoke_agent` avg | Correlate DB and request latency |
| DB Query Duration by Operation | Time Series | avg DB span `Duration` by `db.operation` | Query-type breakdown |

### Span-Tree Exemplar

The Request Performance and Tool & Retrieval rows are best read alongside a single trace in Scout's traceX: open any
`invoke_agent runbook_assistant` span and expand its `retrieval runbooks`, `chat {model}`, and `execute_tool {tool}`
children to see where a slow or failed request spent its time.

### Operational Thresholds & Alerts

| Metric | Warning | Critical | Rationale |
|--------|---------|----------|-----------|
| p99 request duration | 10s | 30s | Tail latency budget |
| Error rate | 1% | 5% | Reliability |
| Tool failures | 1 | 5 | Tool or downstream outage |
| RAG degraded events | 1 | - | Retriever or index problem |

---

## Dashboard 2: Strategic

**Purpose**: Track cost, request volume, token trends, and retrieval/tool efficiency over longer windows.

### Strategic Layout

```plain
┌─────────────────────────────────────────────────────────────────────────────┐
│ HEADER: AI Runbook Assistant — Strategic                 [Time Range]        │
├─────────────────────────────────────────────────────────────────────────────┤
│ FILTERS: [Service ▼] [Model ▼] [Agent ▼] [Provider ▼]                       │
├──────────┬──────────┬──────────┬──────────┬──────────────────────────────┤
│ Requests │ Tool     │ Tool     │ Total    │ Request Success Rate (gauge)  │
│ Processed│ Calls    │ Success  │ Cost     │                               │
├──────────┴──────────┴──────────┴──────────┴──────────────────────────────┤
│ BAR Cost by Provider              │ TS Requests & Token Trend             │
├────────────────────────────────────────────────────────────────────────────┤
│ ROW: Token & Cost Efficiency                                               │
│ Avg Input │ Avg Output │ Cost/1K Tokens │ Avg Cost/Request                 │
│ BAR Input vs Output by Model      │ TABLE Token Usage by Model            │
├────────────────────────────────────────────────────────────────────────────┤
│ ROW: Model A/B Comparison                                                  │
│ TABLE Model Head-to-Head (requests, latency, error rate)                   │
│ TS Latency by Model               │ TS Token Usage by Model               │
├────────────────────────────────────────────────────────────────────────────┤
│ ROW: End-to-End Latency Breakdown                                          │
│ BAR Where Time Goes by Operation (100%)                                    │
│ TS Time by Operation │ TS LLM Time vs Request Time                         │
│ BAR p50/p90/p99 by Operation                                              │
├────────────────────────────────────────────────────────────────────────────┤
│ ROW: Retrieval & Tool Volume                                              │
│ Cost/Request │ Avg Request Dur │ Tools/Request │ Avg Chunks Retrieved      │
│ TABLE Tool Usage Matrix (calls, errors, avg duration by tool)             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Strategic Panel Specifications

| Panel | Type | Data Source | Purpose |
|-------|------|-------------|---------|
| Requests Processed | Stat | `invoke_agent` span count | Volume |
| Tool Calls | Stat | `execute_tool` span count | Tool activity |
| Tool Success Rate | Gauge | (total - errors) / total on `execute_tool` | Tool reliability |
| Total Cost | Stat | `gen_ai.client.cost` increase | Period spend |
| Request Success Rate | Gauge | success on `invoke_agent` | Reliability |
| Cost by Provider | Bar | Group `gen_ai.client.cost` by `gen_ai.provider.name` | Spend attribution |
| Requests & Token Trend | Time Series | request count + `gen_ai.client.token.usage` | Volume vs token load |
| Avg Input / Output Tokens | Stat | `gen_ai.client.token.usage` mean per type | Prompt sizing |
| Cost per 1K Tokens | Stat | cost / tokens * 1000 | Token-cost efficiency |
| Avg Cost / Request | Stat | cost / `invoke_agent` count | Unit economics |
| Input vs Output by Model | Bar | tokens by `gen_ai.request.model` and type | Per-model token shape |
| Token Usage by Model | Table | avg input/output, cost per request by model | Model efficiency drill-down |
| Model Head-to-Head | Table | `chat` spans by `gen_ai.request.model` | Requests, latency, error rate per model |
| Latency by Model | Time Series | avg `chat` `Duration` by model | Model latency trend |
| Token Usage by Model | Time Series | `gen_ai.client.token.usage` by model | Token trend per model |
| Where Time Goes | Bar (100%) | avg `Duration` by `gen_ai.operation.name` | Latency composition |
| Time by Operation | Time Series | avg `Duration` per operation | Latency composition trend |
| LLM Time vs Request Time | Time Series | `chat` avg vs `invoke_agent` avg | LLM share of latency |
| p50/p90/p99 by Operation | Bar | quantiles of `Duration` per operation | Tail latency by stage |
| Cost / Request | Stat | cost / request count | Unit economics |
| Avg Request Duration | Stat | avg `invoke_agent` `Duration` | Baseline latency |
| Tool Calls per Request | Stat | `execute_tool` / `invoke_agent` | Tool intensity |
| Avg Chunks Retrieved | Stat | avg `app.retrieval.chunk_count` | Retrieval volume |
| Tool Usage Matrix | Table | per `gen_ai.tool.name`: calls, errors, avg duration | Tool-level breakdown |

### Strategic Thresholds & Alerts

| Metric | Warning | Critical | Rationale |
|--------|---------|----------|-----------|
| Daily run rate | $10 | $50 | Budget (zero on local Ollama; lights up with a cloud provider) |
| Cost per request | $0.01 | $0.05 | Cost anomaly |
| Avg request duration | 10s | 30s | Latency budget |

> **Cost note**: With a local Ollama provider, `gen_ai.usage.cost_usd` and the cost metrics read zero - this is expected,
> not a failure. The cost panels populate when a paid provider (for example Anthropic) is configured.

### Provider Color Scheme

| Provider | Hex Color | Rationale |
|----------|-----------|-----------|
| Ollama | #6B7280 | Slate (local, no cost) |
| Anthropic | #D97706 | Orange (brand adjacent) |
| OpenAI | #10A37F | OpenAI green |

---

## Data Requirements Summary

### Metrics (from the `gen_ai.client` meter)

| Metric Name | Type | Key Attributes |
|-------------|------|----------------|
| `gen_ai.client.token.usage` | Histogram | `gen_ai.request.model`, `gen_ai.provider.name`, `gen_ai.token.type` |
| `gen_ai.client.operation.duration` | Histogram | `gen_ai.request.model`, `gen_ai.provider.name` |
| `gen_ai.client.cost` | Sum | `gen_ai.request.model`, `gen_ai.provider.name` |
| `gen_ai.client.error.count` | Sum | `gen_ai.provider.name`, `error.type` |

### Spans

| Span Name Pattern | Key Attributes |
|-------------------|----------------|
| `invoke_agent runbook_assistant` | `gen_ai.operation.name=invoke_agent`, `gen_ai.agent.name`, `gen_ai.conversation.id`, status |
| `chat {model}` | `gen_ai.operation.name=chat`, `gen_ai.request.model`, `gen_ai.response.model`, `gen_ai.provider.name`, token + cost attributes |
| `execute_tool {tool}` | `gen_ai.operation.name=execute_tool`, `gen_ai.tool.name`, `gen_ai.tool.type=function` |
| `retrieval runbooks` | `gen_ai.operation.name=retrieval`, `gen_ai.data_source.id=runbooks`, `app.retrieval.chunk_count` |
| SQLAlchemy spans | `db.system=postgresql`, `db.operation` |

### Span Events

| Event Name | Recorded On | Key Attributes |
|------------|-------------|----------------|
| `tool_execution_failed` | parent of a failed `execute_tool` | `error.type` |
| `rag_retrieval_degraded` | parent of a failed `retrieval` | `error.type` |

---

## Design Principles

### Information Hierarchy

- Top row of each section is always Stats/KPIs for immediate status.
- Middle rows are visualizations for analysis.
- Bottom rows are detailed tables for drill-down.

### Consistent Color Coding

- Green means good / success.
- Yellow or orange means warning or attention needed.
- Red means error or failure.
- Blue means informational or input metrics.

### Interaction Patterns

- Filters at the top allow drilling down by service, model, agent, and provider.
- The global time range selector controls every panel.

---

## Base14 Scout Integration

Dashboards give the aggregate view; Scout's explorers handle deep-dive correlation across signals.

- **traceX**: open an `invoke_agent runbook_assistant` span and expand its `retrieval`, `chat`, and `execute_tool`
  children to find the bottleneck in a slow or failed request.
- **logX**: search application logs and jump to the owning trace via auto-injected `trace_id` and `span_id`.
- **pgX**: analyze the SQLAlchemy/PostgreSQL queries behind the Database Impact row, including pgvector retrieval queries.

| Question | Tool | Why |
|----------|------|-----|
| Why is this request slow? | traceX | Span waterfall isolates the slow stage |
| Which tool failed and why? | traceX + logX | `tool_execution_failed` event plus error logs |
| Is the database the problem? | pgX | Query-level latency for the retrieval and history tables |
| What is the overall health? | Dashboards | Aggregate metrics and trends |
