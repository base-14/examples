# AI Sales Intelligence - Dashboard Design Specification

This document describes the conceptual design for observability dashboards. These designs are implementation-agnostic and can be adapted to any visualization platform (Grafana, Datadog, Scout, custom).

---

## Dashboard 1: Token Usage

**Purpose**: Monitor and analyze LLM token consumption patterns

### Layout

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ HEADER: Token Usage Dashboard                            [Time Range] [Refresh] │
├─────────────────────────────────────────────────────────────────────────────┤
│ FILTERS: [Model ▼] [Provider ▼] [Agent ▼]                                   │
├────────────┬────────────┬────────────┬────────────┬────────────────────────┤
│  STAT      │   STAT     │   STAT     │   STAT     │                        │
│  Total     │   Input    │   Output   │  Output/   │  (Reserved for         │
│  Tokens    │   Tokens   │   Tokens   │  Input %   │   future KPIs)         │
│  ████      │   ████     │   ████     │   ██%      │                        │
├────────────┴────────────┴────────────┴────────────┴────────────────────────┤
│ ROW: Token Distribution by Dimension                                        │
├──────────────────────┬──────────────────────┬──────────────────────────────┤
│    DONUT CHART       │    DONUT CHART       │       DONUT CHART            │
│    Tokens by Model   │    Tokens by Provider│       Tokens by Agent        │
│    ┌───┐             │    ┌───┐             │       ┌───┐                  │
│    │ ◐ │ claude-4    │    │ ◐ │ anthropic   │       │ ◐ │ research         │
│    └───┘ gemini-3    │    └───┘ google      │       └───┘ personalize      │
│          gpt-4o      │          openai      │             generate         │
├──────────────────────┴──────────────────────┴──────────────────────────────┤
│ ROW: Token Trends                                                           │
├────────────────────────────────────┬────────────────────────────────────────┤
│     TIME SERIES                    │      TIME SERIES (Stacked Area)       │
│     Input vs Output Over Time      │      Tokens by Model Over Time        │
│     ┌────────────────────┐         │      ┌────────────────────┐           │
│     │  ╱╲  input         │         │      │ ▓▓▓▓▓▓▓▓▓▓ claude  │           │
│     │ ╱  ╲╱╲  output     │         │      │ ░░░░░░░░░░ gemini  │           │
│     └────────────────────┘         │      └────────────────────┘           │
├────────────────────────────────────┴────────────────────────────────────────┤
│ ROW: Distribution Analysis                                                  │
├────────────────────────────────────┬────────────────────────────────────────┤
│     HISTOGRAM                      │      BAR CHART (Horizontal)           │
│     Token Count Distribution       │      Avg Tokens per Request by Agent  │
│     ┌────────────────────┐         │      ┌────────────────────────┐       │
│     │    ▌               │         │      │ research    ████████   │       │
│     │   ▌▌▌              │         │      │ personalize ██████     │       │
│     │  ▌▌▌▌▌             │         │      │ generate    ████       │       │
│     └────────────────────┘         │      └────────────────────────┘       │
└────────────────────────────────────┴────────────────────────────────────────┘
```

### Panel Specifications

| Panel | Type | Data Source | Purpose |
|-------|------|-------------|---------|
| Total Tokens | Stat/KPI | `gen_ai.client.token.usage` sum | Total consumption at a glance |
| Input Tokens | Stat/KPI | `gen_ai.client.token.usage` where `token.type=input` | Prompt size monitoring |
| Output Tokens | Stat/KPI | `gen_ai.client.token.usage` where `token.type=output` | Completion size monitoring |
| Output/Input Ratio | Stat/KPI | Calculated | Efficiency metric |
| Tokens by Model | Donut | Group by `gen_ai.request.model` | Model usage distribution |
| Tokens by Provider | Donut | Group by `gen_ai.provider.name` | Provider comparison |
| Tokens by Agent | Donut | Group by `gen_ai.agent.name` | Agent consumption |
| Input vs Output Time Series | Line | Split by `gen_ai.token.type` | Usage patterns over time |
| Tokens by Model (Stacked) | Stacked Area | Group by `gen_ai.request.model` | Model trends |
| Token Distribution | Histogram | Bucket data | Request size patterns |
| Avg Tokens by Agent | Bar Chart | Avg per agent | Identify verbose agents |

### Thresholds & Alerts

| Metric | Warning | Critical | Rationale |
|--------|---------|----------|-----------|
| Total Tokens/hour | 100K | 500K | Budget protection |
| Output/Input Ratio | <0.5 | <0.2 | Indicates wasted prompt tokens |
| Avg tokens per request | 500 | 1000 | Identifies bloated prompts |

---

## Dashboard 2: Cost Attribution

**Purpose**: Track LLM spending and attribute costs to business dimensions

### Layout

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ HEADER: Cost Attribution Dashboard                       [Time Range] [Refresh] │
├─────────────────────────────────────────────────────────────────────────────┤
│ FILTERS: [Model ▼] [Agent ▼] [Campaign ▼]                                   │
├────────────┬────────────┬────────────┬────────────┬────────────────────────┤
│  STAT      │   STAT     │   STAT     │   STAT     │                        │
│  Total     │   Avg Cost │   Daily    │  Cost per  │  (Budget gauge or      │
│  Cost      │   /Request │   Run Rate │  1K Tokens │   burn rate)           │
│  $0.0234   │   $0.0001  │   $5.62    │   $0.003   │                        │
├────────────┴────────────┴────────────┴────────────┴────────────────────────┤
│ ROW: Cost Attribution                                                       │
├──────────────────────┬──────────────────────┬──────────────────────────────┤
│    DONUT CHART       │    DONUT CHART       │       DONUT CHART            │
│    Cost by Model     │    Cost by Agent     │       Cost by Provider       │
│    ┌───┐             │    ┌───┐             │       ┌───┐                  │
│    │ ◐ │ claude-4    │    │ ◐ │ generate    │       │ ◐ │ anthropic (D97706)│
│    └───┘ 65%         │    └───┘ 40%         │       └───┘ google (4285F4)  │
│          gemini 30%  │          research 35%│             openai (10A37F)  │
├──────────────────────┴──────────────────────┴──────────────────────────────┤
│ ROW: Campaign Cost Attribution                                              │
├────────────────────────────────────┬────────────────────────────────────────┤
│     BAR CHART (Horizontal)         │      STACKED BAR CHART                 │
│     Total Cost by Campaign         │      Cost by Campaign & Agent          │
│     ┌────────────────────┐         │      ┌────────────────────────┐       │
│     │ camp-001 ████████  │         │      │ camp-001 ▓▓░░▒▒       │       │
│     │ camp-002 ██████    │         │      │ camp-002 ▓▓░░▒▒       │       │
│     │ camp-003 ████      │         │      │ camp-003 ▓░▒          │       │
│     └────────────────────┘         │      └────────────────────────┘       │
├────────────────────────────────────┴────────────────────────────────────────┤
│ ROW: Cost Trends                                                            │
├────────────────────────────────────┬────────────────────────────────────────┤
│     TIME SERIES (Cumulative)       │      TIME SERIES (Stacked Area)       │
│     Cumulative Cost Over Time      │      Cost Rate by Model               │
│     ┌────────────────────┐         │      ┌────────────────────┐           │
│     │        ╱           │         │      │ ▓▓▓▓▓▓▓▓ claude     │           │
│     │      ╱             │         │      │ ░░░░░░░░ gemini     │           │
│     │    ╱               │         │      │ ▒▒▒▒▒▒▒▒ gpt        │           │
│     └────────────────────┘         │      └────────────────────┘           │
├────────────────────────────────────┴────────────────────────────────────────┤
│ ROW: Cost Efficiency                                                        │
├────────────────────────────────────┬────────────────────────────────────────┤
│     BAR CHART (Horizontal)         │      TABLE                             │
│     Cost per Request by Agent      │      Model Cost Comparison             │
│     ┌────────────────────┐         │      ┌─────────────────────────────┐  │
│     │ research   ████    │         │      │ Model     │ Cost  │ Tokens │  │
│     │ generate   ██████  │         │      │ claude-4  │ $0.01 │  2.3K  │  │
│     │ personalize████    │         │      │ gemini-3  │ $0.002│  1.8K  │  │
│     └────────────────────┘         │      └─────────────────────────────┘  │
└────────────────────────────────────┴────────────────────────────────────────┘
```

### Panel Specifications

| Panel | Type | Data Source | Purpose |
|-------|------|-------------|---------|
| Total Cost | Stat/KPI | `gen_ai.client.cost` sum | Period spend |
| Avg Cost/Request | Stat/KPI | cost / request_count | Unit economics |
| Daily Run Rate | Stat/KPI | rate * 86400 | Projection |
| Cost per 1K Tokens | Stat/KPI | cost / tokens * 1000 | Efficiency |
| Cost by Model | Donut | Group by `gen_ai.request.model` | Model spend |
| Cost by Agent | Donut | Group by `gen_ai.agent.name` | Agent spend |
| Cost by Provider | Donut | Group by `gen_ai.provider.name` | Provider spend |
| Cost by Campaign | Bar | Group by `campaign_id` | Campaign ROI |
| Cost by Campaign & Agent | Stacked Bar | Group by campaign + agent | Detailed attribution |
| Cumulative Cost | Time Series | Running total | Budget tracking |
| Cost Rate by Model | Stacked Area | Rate per model | Trend analysis |
| Cost per Request by Agent | Bar | cost/requests per agent | Agent efficiency |
| Model Cost Comparison | Table | All dimensions | Side-by-side comparison |

### Thresholds & Alerts

| Metric | Warning | Critical | Rationale |
|--------|---------|----------|-----------|
| Daily run rate | $10 | $50 | Budget alert |
| Cost per request | $0.01 | $0.05 | Cost anomaly |
| Cost spike | 2x baseline | 5x baseline | Runaway costs |

### Provider Color Scheme

| Provider | Hex Color | Rationale |
|----------|-----------|-----------|
| Anthropic | #D97706 | Orange (brand adjacent) |
| Google | #4285F4 | Google Blue |
| OpenAI | #10A37F | OpenAI Green |

---

## Dashboard 3: Quality Metrics

**Purpose**: Monitor email generation quality and evaluation results

### Layout

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ HEADER: Quality Metrics Dashboard                        [Time Range] [Refresh] │
├─────────────────────────────────────────────────────────────────────────────┤
│ FILTERS: [Model ▼] [Campaign ▼]                                             │
├────────────┬────────────┬────────────┬────────────┬────────────────────────┤
│   GAUGE    │   GAUGE    │   STAT     │   STAT     │      STAT              │
│   Pass     │   Avg      │   Total    │   Passed   │      Failed            │
│   Rate     │   Score    │   Evaluated│            │                        │
│   [==85%]  │   [==78]   │   1,234    │   1,049    │      185               │
│   ▓▓▓▓░░   │   ▓▓▓▓░░   │            │   (green)  │      (red)             │
├────────────┴────────────┴────────────┴────────────┴────────────────────────┤
│ ROW: Quality Trends                                                         │
├────────────────────────────────────┬────────────────────────────────────────┤
│     TIME SERIES                    │      TIME SERIES (Stacked Bar)        │
│     Quality Score Over Time        │      Pass/Fail Over Time              │
│     ┌────────────────────┐         │      ┌────────────────────┐           │
│     │    ╱╲   threshold  │         │      │ ▓▓▓▓▓▓▓▓▓▓ passed  │           │
│     │  ╱   ╲  --------   │         │      │ ░░░░░░░░░░ failed  │           │
│     │ ╱      ╲           │         │      │ ▓▓▓▓▓▓▓▓░░         │           │
│     └────────────────────┘         │      └────────────────────┘           │
│     (with threshold line @ 70)     │                                        │
├────────────────────────────────────┴────────────────────────────────────────┤
│ ROW: Score Distribution                                                     │
├────────────────────────────────────┬────────────────────────────────────────┤
│     HISTOGRAM                      │      TIME SERIES (Multi-line)         │
│     Score Distribution             │      Score Percentiles (p50/p90/p99)  │
│     ┌────────────────────┐         │      ┌────────────────────┐           │
│     │          ▌▌        │         │      │ ─── p99            │           │
│     │        ▌▌▌▌        │         │      │ ─ ─ p90            │           │
│     │      ▌▌▌▌▌▌▌       │         │      │ ··· p50            │           │
│     │ 0   40   70  100   │         │      └────────────────────┘           │
│     └────────────────────┘         │                                        │
│     (highlight <70 in red)         │                                        │
├────────────────────────────────────┴────────────────────────────────────────┤
│ ROW: Quality by Dimension                                                   │
├────────────────────────────────────┬────────────────────────────────────────┤
│     BAR CHART (Horizontal)         │      BAR CHART (Horizontal)           │
│     Avg Quality Score by Model     │      Pass Rate by Model               │
│     ┌────────────────────┐         │      ┌────────────────────┐           │
│     │ claude-4   ████████│         │      │ claude-4   ████████│ 92%       │
│     │ gemini-3   ███████ │         │      │ gemini-3   ███████ │ 85%       │
│     │ gpt-4o     ██████  │         │      │ gpt-4o     █████   │ 78%       │
│     └────────────────────┘         │      └────────────────────┘           │
│     (color by threshold)           │      (color by threshold)             │
├────────────────────────────────────┴────────────────────────────────────────┤
│ ROW: Campaign Quality Summary                                               │
├─────────────────────────────────────────────────────────────────────────────┤
│     TABLE                                                                   │
│     Quality Summary by Campaign                                             │
│     ┌───────────────────────────────────────────────────────────────────┐  │
│     │ Campaign  │ Evaluated │ Passed │ Failed │ Avg Score │ Pass Rate  │  │
│     │ camp-001  │    450    │   405  │   45   │    82     │ ▓▓▓▓░ 90%  │  │
│     │ camp-002  │    380    │   304  │   76   │    75     │ ▓▓▓░░ 80%  │  │
│     │ camp-003  │    404    │   340  │   64   │    78     │ ▓▓▓▓░ 84%  │  │
│     └───────────────────────────────────────────────────────────────────┘  │
│     (Pass Rate column as inline gauge)                                      │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Panel Specifications

| Panel | Type | Data Source | Purpose |
|-------|------|-------------|---------|
| Pass Rate | Gauge | passed / total * 100 | Overall quality KPI |
| Avg Score | Gauge | avg(score_value) | Quality level |
| Total Evaluated | Stat | count of evaluations | Volume |
| Passed/Failed | Stat pair | count by label | Quick status |
| Score Over Time | Time Series | avg score with threshold line | Quality trend |
| Pass/Fail Over Time | Stacked Bar | count by label | Volume + quality |
| Score Distribution | Histogram | bucket data | Identify score clustering |
| Score Percentiles | Multi-line | p50, p90, p99 | Quality consistency |
| Avg Score by Model | Bar | avg score per model | Model quality comparison |
| Pass Rate by Model | Bar | pass rate per model | Model reliability |
| Campaign Summary | Table | All metrics by campaign | Detailed breakdown |

### Evaluation Event Attributes (from `gen_ai.evaluation.result`)

| Attribute | Type | Purpose |
|-----------|------|---------|
| `gen_ai.evaluation.name` | string | Evaluation type (e.g., "email_quality") |
| `gen_ai.evaluation.score.value` | float | Numeric score (0-100) |
| `gen_ai.evaluation.score.label` | string | "passed" or "failed" |
| `gen_ai.evaluation.explanation` | string | Feedback text |

### Thresholds

| Metric | Good | Warning | Critical |
|--------|------|---------|----------|
| Pass Rate | >85% | 70-85% | <70% |
| Avg Score | >80 | 60-80 | <60 |
| p99 Score | >60 | 40-60 | <40 |

---

## Dashboard 4: Pipeline Performance

**Purpose**: Monitor agent execution performance and error rates

### Layout

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ HEADER: Pipeline Performance Dashboard                   [Time Range] [Refresh] │
├─────────────────────────────────────────────────────────────────────────────┤
│ FILTERS: [Agent ▼] [Campaign ▼]                                             │
├────────────┬────────────┬────────────┬────────────┬────────────────────────┤
│   STAT     │   STAT     │   STAT     │   GAUGE    │                        │
│   Total    │   Avg      │   p99      │   Success  │   (Error count or      │
│   Pipelines│   Duration │   Duration │   Rate     │    throughput)         │
│   1,234    │   4.2s     │   12.8s    │   98.5%    │                        │
├────────────┴────────────┴────────────┴────────────┴────────────────────────┤
│ ROW: Agent Performance                                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│     BAR CHART (Horizontal, Grouped)                                         │
│     Agent Duration Comparison (p50, p90, p99)                               │
│     ┌───────────────────────────────────────────────────────────────────┐  │
│     │ research     ▓▓▓▓░░▒▒                                             │  │
│     │ personalize  ▓▓░░▒                                                │  │
│     │ generate     ▓▓▓▓▓▓░░░▒▒▒                                         │  │
│     │ evaluate     ▓░                                                   │  │
│     │              ▓ p50  ░ p90  ▒ p99                                  │  │
│     └───────────────────────────────────────────────────────────────────┘  │
├────────────────────────────────────────────────────────────────────────────┤
│ ROW: Duration Trends                                                        │
├────────────────────────────────────┬────────────────────────────────────────┤
│     TIME SERIES                    │      TIME SERIES (Stacked Area)       │
│     Overall Duration Percentiles   │      Duration by Agent                │
│     ┌────────────────────┐         │      ┌────────────────────┐           │
│     │ ─── p99            │         │      │ ▓▓▓ research        │           │
│     │ ─ ─ p90            │         │      │ ░░░ personalize     │           │
│     │ ··· p50            │         │      │ ▒▒▒ generate        │           │
│     └────────────────────┘         │      └────────────────────┘           │
├────────────────────────────────────┴────────────────────────────────────────┤
│ ROW: Error Analysis                                                         │
├──────────────────────┬──────────────────────┬──────────────────────────────┤
│    STAT              │    DONUT CHART       │       TIME SERIES            │
│    Error Count       │    Errors by Agent   │       Error Rate Over Time   │
│    ┌───────┐         │    ┌───┐             │       ┌────────────────┐     │
│    │  23   │         │    │ ◐ │ generate    │       │     ╱╲          │     │
│    │ (red) │         │    └───┘ research    │       │    ╱  ╲         │     │
│    └───────┘         │          evaluate    │       └────────────────┘     │
├──────────────────────┴──────────────────────┴──────────────────────────────┤
│ ROW: Throughput & Concurrency                                               │
├────────────────────────────────────┬────────────────────────────────────────┤
│     TIME SERIES                    │      HEATMAP                          │
│     Pipeline Throughput (req/min)  │      Request Duration Heatmap         │
│     ┌────────────────────┐         │      ┌────────────────────┐           │
│     │    ╱╲              │         │      │ █▓▒░   ░▒▓█        │           │
│     │  ╱    ╲            │         │      │ duration buckets   │           │
│     │ ╱        ╲         │         │      │ over time          │           │
│     └────────────────────┘         │      └────────────────────┘           │
├────────────────────────────────────┴────────────────────────────────────────┤
│ ROW: Agent Execution Table                                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│     TABLE                                                                   │
│     Agent Performance Summary                                               │
│     ┌───────────────────────────────────────────────────────────────────┐  │
│     │ Agent       │ Calls │ p50   │ p99   │ Errors │ Error %  │ Tokens │  │
│     │ research    │  450  │ 2.1s  │ 5.4s  │   3    │ ▓░░ 0.7% │  45K   │  │
│     │ personalize │  450  │ 1.8s  │ 4.2s  │   2    │ ▓░░ 0.4% │  32K   │  │
│     │ generate    │  450  │ 3.2s  │ 8.1s  │  15    │ ▓▓░ 3.3% │  89K   │  │
│     │ evaluate    │  450  │ 0.9s  │ 2.1s  │   3    │ ▓░░ 0.7% │  28K   │  │
│     └───────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Panel Specifications

| Panel | Type | Data Source | Purpose |
|-------|------|-------------|---------|
| Total Pipelines | Stat | pipeline span count | Volume |
| Avg Duration | Stat | avg(duration) | Baseline perf |
| p99 Duration | Stat | p99(duration) | Worst case |
| Success Rate | Gauge | (total - errors) / total | Reliability |
| Agent Duration (Grouped) | Grouped Bar | p50/p90/p99 per agent | Agent comparison |
| Duration Percentiles | Multi-line Time Series | p50/p90/p99 over time | Performance trends |
| Duration by Agent | Stacked Area | duration per agent | Time breakdown |
| Error Count | Stat | count of errors | Quick status |
| Errors by Agent | Donut | errors grouped by agent | Error attribution |
| Error Rate Over Time | Time Series | error rate | Error trends |
| Pipeline Throughput | Time Series | requests/minute | Capacity planning |
| Duration Heatmap | Heatmap | duration distribution | Pattern detection |
| Agent Performance Table | Table | All metrics | Detailed view |

### Span Attributes (from `invoke_agent {name}`)

| Attribute | Type | Purpose |
|-----------|------|---------|
| `gen_ai.operation.name` | string | "invoke_agent" |
| `gen_ai.agent.name` | string | Agent identifier |
| `campaign_id` | string | Campaign attribution |
| Span duration | float | Execution time |
| Span status | enum | OK/ERROR |
| `error.type` | string | Error classification |

### Thresholds

| Metric | Good | Warning | Critical |
|--------|------|---------|----------|
| p99 Duration | <10s | 10-30s | >30s |
| Error Rate | <1% | 1-5% | >5% |
| Throughput drop | - | 50% drop | 80% drop |

---

## Dashboard 5: Executive Summary (Optional)

**Purpose**: High-level overview for stakeholders

### Layout

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ HEADER: AI Sales Intelligence - Executive Summary        [Time Range]        │
├─────────────────────────────────────────────────────────────────────────────┤
│ ROW: Key Metrics                                                            │
├────────────┬────────────┬────────────┬────────────┬────────────────────────┤
│   STAT     │   STAT     │   STAT     │   STAT     │      TREND SPARKLINE   │
│   Campaigns│   Emails   │   Quality  │   Total    │      ┌──────────┐     │
│   Processed│   Generated│   Pass Rate│   Cost     │      │  ╱╲╱     │     │
│   234      │   1,872    │   87%      │   $42.56   │      └──────────┘     │
├────────────┴────────────┴────────────┴────────────┴────────────────────────┤
│ ROW: Performance at a Glance                                                │
├──────────────────────────────────────┬──────────────────────────────────────┤
│     GAUGE PANEL (3 gauges)           │      BAR CHART                       │
│     ┌────────┬────────┬────────┐     │      Cost by Provider               │
│     │Quality │Success │Budget  │     │      ┌────────────────────┐         │
│     │ 87%    │ 98%    │ 43%    │     │      │ Anthropic ████████ │         │
│     │▓▓▓▓░   │▓▓▓▓▓   │▓▓░░░   │     │      │ Google    ████     │         │
│     └────────┴────────┴────────┘     │      │ OpenAI    ██       │         │
│                                       │      └────────────────────┘         │
├──────────────────────────────────────┴──────────────────────────────────────┤
│ ROW: Trend Overview                                                         │
├─────────────────────────────────────────────────────────────────────────────┤
│     TIME SERIES (Multi-metric)                                              │
│     Campaigns, Quality, Cost (Normalized)                                   │
│     ┌───────────────────────────────────────────────────────────────────┐  │
│     │    campaigns ────                                                 │  │
│     │    quality   ─ ─ ─                                                │  │
│     │    cost      · · ·                                                │  │
│     └───────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Design Principles

### 1. Information Hierarchy
- **Top row**: Always KPIs/Stats for immediate status
- **Middle rows**: Visualizations for analysis
- **Bottom rows**: Detailed tables for drill-down

### 2. Consistent Color Coding
| Color | Meaning |
|-------|---------|
| Green | Good / Success / Passed |
| Yellow/Orange | Warning / Attention needed |
| Red | Critical / Error / Failed |
| Blue | Informational / Input metrics |

### 3. Interaction Patterns
- **Filters at top**: Allow drilling down by model, agent, campaign
- **Linked panels**: Clicking one panel filters others
- **Time range selector**: Global time range control

### 4. Responsive Considerations
- Panels should collapse gracefully on smaller screens
- Stats/KPIs remain visible; charts can scroll
- Tables should support horizontal scrolling

---

## Data Requirements Summary

### Metrics (from `gen_ai.client` meter)

| Metric Name | Type | Key Attributes |
|-------------|------|----------------|
| `gen_ai.client.token.usage` | Histogram | model, provider, agent, token.type |
| `gen_ai.client.operation.duration` | Histogram | model, provider, agent |
| `gen_ai.client.cost` | Counter | model, provider, agent, campaign_id |

### Spans

| Span Name Pattern | Key Attributes |
|-------------------|----------------|
| `gen_ai.chat {model}` | model, provider, tokens, cost, agent, campaign |
| `invoke_agent {name}` | agent.name, campaign_id, status |

### Events

| Event Name | Key Attributes |
|------------|----------------|
| `gen_ai.evaluation.result` | name, score.value, score.label, explanation |

---

## Implementation Notes

1. **Start simple**: Implement Dashboard 1 (Token Usage) first, then add others
2. **Iterate on thresholds**: Adjust warning/critical levels based on actual usage patterns
3. **Add annotations**: Mark deployments, incidents, config changes on time series

---

## Base14 Scout Integration

While dashboards provide aggregate views of system health, **Base14 Scout** offers specialized explorers for deep-dive debugging and correlation across telemetry signals.

### traceX (Trace Explorer)

**Purpose**: Verify and debug distributed trace spans across the LangGraph pipeline

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ traceX - Trace Explorer                                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Use traceX to:                                                             │
│                                                                             │
│  • Visualize end-to-end pipeline execution                                  │
│    ┌──────────────────────────────────────────────────────────────────┐    │
│    │ POST /campaigns/{id}/run                                         │    │
│    │ └─ invoke_agent research         [2.1s]  ████████                │    │
│    │    └─ gen_ai.chat claude-sonnet  [1.8s]  ███████                 │    │
│    │       └─ HTTP POST api.anthropic.com                             │    │
│    │ └─ invoke_agent personalize      [1.5s]  ██████                  │    │
│    │    └─ gen_ai.chat claude-sonnet  [1.2s]  █████                   │    │
│    │ └─ invoke_agent generate         [3.2s]  █████████████           │    │
│    │    └─ gen_ai.chat claude-sonnet  [2.9s]  ████████████            │    │
│    │ └─ invoke_agent evaluate         [0.8s]  ███                     │    │
│    └──────────────────────────────────────────────────────────────────┘    │
│                                                                             │
│  • Inspect GenAI span attributes                                            │
│    - gen_ai.usage.input_tokens: 1,234                                       │
│    - gen_ai.usage.output_tokens: 456                                        │
│    - gen_ai.usage.cost_usd: 0.0089                                          │
│    - gen_ai.agent.name: "generate"                                          │
│    - campaign_id: "camp-001"                                                │
│                                                                             │
│  • Filter traces by:                                                        │
│    - gen_ai.agent.name = "generate" (find slow generators)                  │
│    - gen_ai.provider.name = "anthropic" (provider-specific issues)          │
│    - campaign_id = "camp-xyz" (campaign debugging)                          │
│    - error.type exists (find all errors)                                    │
│                                                                             │
│  • Compare traces side-by-side                                              │
│    - Fast vs slow executions                                                │
│    - Successful vs failed pipelines                                         │
│    - Different models/providers                                             │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Key Use Cases**:
| Scenario | How traceX Helps |
|----------|------------------|
| Slow pipeline | Identify which agent/LLM call is the bottleneck |
| Failed generation | See exact error, span context, and retry attempts |
| Cost spike | Trace high-token requests to specific campaigns |
| Quality issue | Correlate low evaluation scores with generation spans |

---

### logX (Log Explorer)

**Purpose**: Search logs and correlate with traces for faster issue discovery

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ logX - Log Explorer                                                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Use logX to:                                                               │
│                                                                             │
│  • Search and filter logs                                                   │
│    ┌──────────────────────────────────────────────────────────────────┐    │
│    │ [Search: level:ERROR AND "LLM" ]                     [Last 1h ▼] │    │
│    ├──────────────────────────────────────────────────────────────────┤    │
│    │ 14:32:15 ERROR LLM rate limit exceeded, retrying...              │    │
│    │          trace_id: abc123  span_id: def456                       │    │
│    │          → [View Trace]                                          │    │
│    │ 14:31:02 ERROR LLM response validation failed                    │    │
│    │          trace_id: ghi789  span_id: jkl012                       │    │
│    │          → [View Trace]                                          │    │
│    └──────────────────────────────────────────────────────────────────┘    │
│                                                                             │
│  • Correlate logs with traces (automatic trace_id injection)                │
│    - Click any log → jump to full trace in traceX                           │
│    - See all logs within a trace context                                    │
│    - Filter: trace_id="abc123" to see all logs for one request              │
│                                                                             │
│  • Discover issues faster                                                   │
│    - Aggregate logs by error type                                           │
│    - Pattern detection: "rate limit" appearing 50x in last hour             │
│    - Timeline view: when did errors start?                                  │
│                                                                             │
│  • Log-to-trace workflow                                                    │
│    1. Search logs: "evaluation failed"                                      │
│    2. Click log entry → opens trace                                         │
│    3. See full pipeline context around the failure                          │
│    4. Identify root cause (e.g., upstream agent returned bad data)          │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Key Use Cases**:
| Scenario | How logX Helps |
|----------|----------------|
| Production error | Search error logs, jump to trace for context |
| Intermittent failures | Find patterns in error timing/frequency |
| Debug specific request | Filter by trace_id to see all related logs |
| Audit trail | Search by campaign_id for compliance review |

**Log Correlation Attributes** (auto-injected by OTel LoggingInstrumentor):
- `trace_id`: Links log to distributed trace
- `span_id`: Links log to specific operation
- `service.name`: Identifies service origin

---

### pgX (PostgreSQL Explorer)

**Purpose**: Monitor PostgreSQL performance and correlate with application traces

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ pgX - PostgreSQL Explorer                                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Use pgX to:                                                                │
│                                                                             │
│  • Monitor query performance                                                │
│    ┌──────────────────────────────────────────────────────────────────┐    │
│    │ Slow Queries (>100ms)                                            │    │
│    ├──────────────────────────────────────────────────────────────────┤    │
│    │ 245ms  SELECT * FROM campaigns WHERE id = $1                     │    │
│    │        calls: 1,234  avg: 12ms  p99: 245ms                       │    │
│    │        → [View Traces] [Explain Plan]                            │    │
│    │                                                                  │    │
│    │ 189ms  INSERT INTO generated_emails (campaign_id, content...)    │    │
│    │        calls: 892  avg: 45ms  p99: 189ms                         │    │
│    │        → [View Traces] [Explain Plan]                            │    │
│    └──────────────────────────────────────────────────────────────────┘    │
│                                                                             │
│  • Correlate DB queries with application traces                             │
│    - Click query → see all traces that executed this query                  │
│    - Identify which agents trigger expensive queries                        │
│    - Find N+1 query patterns in pipeline execution                          │
│                                                                             │
│  • Database health overview                                                 │
│    ┌────────────┬────────────┬────────────┬────────────┐                   │
│    │ Connections│ Query/sec  │ Avg Latency│ Cache Hit  │                   │
│    │    24/100  │   156      │   8.2ms    │   98.5%    │                   │
│    └────────────┴────────────┴────────────┴────────────┘                   │
│                                                                             │
│  • Full correlation workflow                                                │
│    1. Dashboard shows p99 latency spike                                     │
│    2. pgX identifies slow INSERT on generated_emails                        │
│    3. Click → traceX shows it's the "generate" agent                        │
│    4. logX shows disk I/O warnings at same time                             │
│    5. Root cause: batch insert during high LLM throughput                   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Key Use Cases**:
| Scenario | How pgX Helps |
|----------|---------------|
| Slow API response | Identify if DB queries are the bottleneck |
| Connection exhaustion | Monitor pool usage, find connection leaks |
| Query regression | Compare query performance before/after deployment |
| FTS optimization | Analyze PostgreSQL full-text search patterns and index usage |

**Database Spans** (auto-instrumented by SQLAlchemyInstrumentor):
- `db.system`: "postgresql"
- `db.statement`: SQL query text
- `db.operation`: SELECT/INSERT/UPDATE/DELETE
- Span duration: Query execution time

---

### Scout Correlation Workflow

The power of Base14 Scout is **seamless correlation** across all three explorers:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        Scout Correlation Workflow                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Dashboard Alert                                                           │
│   "Quality pass rate dropped to 65%"                                        │
│         │                                                                   │
│         ▼                                                                   │
│   ┌─────────────────┐                                                       │
│   │     traceX      │  Filter: gen_ai.evaluation.score.label = "failed"     │
│   │   (traces)      │  → Find traces where evaluation failed                │
│   └────────┬────────┘                                                       │
│            │ "Many failures have slow generate agent spans"                 │
│            ▼                                                                │
│   ┌─────────────────┐                                                       │
│   │      logX       │  Filter: trace_id IN (failed traces)                  │
│   │    (logs)       │  → See "LLM timeout" warnings before failures         │
│   └────────┬────────┘                                                       │
│            │ "Timeouts correlate with high DB latency"                      │
│            ▼                                                                │
│   ┌─────────────────┐                                                       │
│   │      pgX        │  Check query performance at failure times             │
│   │  (postgresql)   │  → Connection pool saturated, queries queuing         │
│   └────────┬────────┘                                                       │
│            │                                                                │
│            ▼                                                                │
│   Root Cause: DB connection starvation causing LLM timeouts,                │
│               leading to incomplete generations and failed evaluations      │
│                                                                             │
│   Fix: Increase pool_size in database.py from 10 to 25                      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### When to Use Each Tool

| Question | Tool | Why |
|----------|------|-----|
| "Why is this request slow?" | traceX | See full span waterfall, identify bottleneck |
| "What errors happened?" | logX | Search/filter logs, see patterns |
| "Is the DB the problem?" | pgX | Query-level performance analysis |
| "What caused this alert?" | All three | Correlate across signals |
| "What's the overall health?" | Dashboards | Aggregate metrics, trends |

### Configuration for Scout Integration

The application is already configured to export telemetry to Scout via the OTel Collector:

```yaml
# otel-collector-config.yaml
exporters:
  otlphttp/b14:
    endpoint: ${SCOUT_ENDPOINT}
    auth:
      authenticator: oauth2client
```

All three explorers (traceX, logX, pgX) automatically receive:
- **Traces**: From FastAPI, SQLAlchemy, httpx auto-instrumentation + custom GenAI spans
- **Logs**: With trace correlation via LoggingInstrumentor
- **DB metrics**: From SQLAlchemy instrumentation with query details

---

## Additional Dashboards for AI/LLM Improvement

The following dashboards are designed to **integrate tightly with Scout explorers** and enable continuous AI/LLM application improvement.

### Dashboard 6: LLM Error & Retry Analysis

**Purpose**: Understand failure patterns and improve reliability

**Scout Integration**: Links to traceX for failed traces, logX for error patterns

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ LLM Error & Retry Analysis                               [Time Range]       │
├─────────────────────────────────────────────────────────────────────────────┤
│ ROW: Error Overview                                                         │
├────────────┬────────────┬────────────┬────────────┬────────────────────────┤
│   STAT     │   STAT     │   STAT     │   GAUGE    │      STAT              │
│   Total    │   Retry    │   Fallback │   Success  │      Avg Retries       │
│   Errors   │   Count    │   Triggered│   After    │      per Request       │
│   47       │   156      │   23       │   Retry    │      1.2               │
│   (red)    │   (yellow) │   (orange) │   89%      │                        │
├────────────┴────────────┴────────────┴────────────┴────────────────────────┤
│ ROW: Error Classification                                                   │
├────────────────────────────────────┬────────────────────────────────────────┤
│     DONUT CHART                    │      BAR CHART (Horizontal)           │
│     Errors by Type                 │      Errors by Provider               │
│     ┌───┐                          │      ┌────────────────────────┐       │
│     │ ◐ │ RateLimitError (45%)     │      │ anthropic  ████████    │       │
│     └───┘ TimeoutError (30%)       │      │ google     ████        │       │
│           ValidationError (15%)    │      │ openai     ██          │       │
│           ConnectionError (10%)    │      └────────────────────────┘       │
│                                    │      → [View in logX]                 │
├────────────────────────────────────┴────────────────────────────────────────┤
│ ROW: Error Timeline & Patterns                                              │
├────────────────────────────────────┬────────────────────────────────────────┤
│     TIME SERIES                    │      TABLE                             │
│     Errors Over Time by Type       │      Recent Errors (Clickable)        │
│     ┌────────────────────┐         │      ┌─────────────────────────────┐  │
│     │ ▓ rate_limit       │         │      │ Time  │ Type    │ Agent    │  │
│     │ ░ timeout          │         │      │ 14:32 │ Timeout │ generate │  │
│     │ ▒ validation       │         │      │       │ → [traceX] [logX]  │  │
│     └────────────────────┘         │      │ 14:31 │ RateLimit│ research│  │
│     → [Correlate in logX]          │      │       │ → [traceX] [logX]  │  │
│                                    │      └─────────────────────────────┘  │
├────────────────────────────────────┴────────────────────────────────────────┤
│ ROW: Retry & Fallback Effectiveness                                         │
├─────────────────────────────────────────────────────────────────────────────┤
│     SANKEY DIAGRAM                                                          │
│     Request Flow: Initial → Retry → Fallback → Outcome                      │
│     ┌───────────────────────────────────────────────────────────────────┐  │
│     │  Requests ──┬── Success (85%) ─────────────────────── ✓ Success   │  │
│     │  (1000)     │                                                     │  │
│     │             ├── Retry (12%) ──┬── Success (89%) ───── ✓ Success   │  │
│     │             │                 └── Fallback (11%) ─┬─ ✓ Success    │  │
│     │             │                                     └─ ✗ Failed     │  │
│     │             └── Failed (3%) ──────────────────────── ✗ Failed     │  │
│     └───────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

**AI/LLM Improvement Actions**:
| Insight | Action | Scout Deep Dive |
|---------|--------|-----------------|
| High rate limit errors | Implement request queuing or switch provider | logX: search "rate limit" |
| Frequent timeouts on generate agent | Optimize prompt length or increase timeout | traceX: filter slow generate spans |
| Fallback success rate low | Improve fallback model/prompt compatibility | traceX: compare primary vs fallback |

---

### Dashboard 7: Prompt Efficiency & Engineering

**Purpose**: Optimize prompts for better quality and lower cost

**Scout Integration**: traceX for individual prompt analysis, compare high vs low quality traces

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Prompt Efficiency & Engineering                          [Time Range]       │
├─────────────────────────────────────────────────────────────────────────────┤
│ ROW: Efficiency Metrics                                                     │
├────────────┬────────────┬────────────┬────────────┬────────────────────────┤
│   STAT     │   STAT     │   STAT     │   STAT     │      TREND             │
│   Avg      │   Avg      │   Quality  │   Cost per │      ┌──────────┐     │
│   Input    │   Output   │   per      │   Quality  │      │  ↘       │     │
│   Tokens   │   Tokens   │   Token    │   Point    │      └──────────┘     │
│   892      │   234      │   0.087    │   $0.0012  │      (improving)       │
├────────────┴────────────┴────────────┴────────────┴────────────────────────┤
│ ROW: Token Efficiency by Agent                                              │
├─────────────────────────────────────────────────────────────────────────────┤
│     GROUPED BAR CHART                                                       │
│     Input vs Output Tokens by Agent (Identify Verbose Prompts)              │
│     ┌───────────────────────────────────────────────────────────────────┐  │
│     │ research     ▓▓▓▓▓▓▓▓░░░░    input: 1200  output: 450             │  │
│     │ personalize  ▓▓▓▓░░           input: 600   output: 200             │  │
│     │ generate     ▓▓▓▓▓▓▓▓▓▓▓▓░░░░░░░░  input: 1800  output: 800       │  │
│     │ evaluate     ▓▓▓░              input: 400   output: 150             │  │
│     │              ▓ input  ░ output                                     │  │
│     └───────────────────────────────────────────────────────────────────┘  │
│     → [View high-token traces in traceX]                                    │
├────────────────────────────────────────────────────────────────────────────┤
│ ROW: Quality vs Token Analysis                                              │
├────────────────────────────────────┬────────────────────────────────────────┤
│     SCATTER PLOT                   │      HEATMAP                          │
│     Quality Score vs Input Tokens  │      Token Count vs Quality Buckets   │
│     ┌────────────────────┐         │      ┌────────────────────┐           │
│     │     ·  · ·         │         │      │ Tokens │ Q<60│60-80│>80│       │
│     │   · · ·· ·         │         │      │ <500   │ ░░░ │ ▒▒▒ │ ▓▓ │       │
│     │  ·  ·    ·         │         │      │ 500-1K │ ░░  │ ▒▒▒▒│ ▓▓▓│       │
│     │ Quality ↑          │         │      │ >1K    │ ░   │ ▒▒  │ ▓▓▓│       │
│     │    Tokens →        │         │      └────────────────────┘           │
│     └────────────────────┘         │      → More tokens ≠ better quality   │
│     → [Click dots to view trace]   │                                        │
├────────────────────────────────────┴────────────────────────────────────────┤
│ ROW: Prompt Optimization Opportunities                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│     TABLE                                                                   │
│     Agents with Optimization Potential                                      │
│     ┌───────────────────────────────────────────────────────────────────┐  │
│     │ Agent      │ Avg Input │ Quality │ Cost/Req │ Opportunity        │  │
│     │ generate   │   1,800   │   78    │  $0.012  │ 🔴 High tokens,    │  │
│     │            │           │         │          │    moderate quality│  │
│     │            │           │         │          │ → [Compare in traceX]│ │
│     │ research   │   1,200   │   85    │  $0.008  │ 🟡 Review for      │  │
│     │            │           │         │          │    compression     │  │
│     │ personalize│    600    │   82    │  $0.004  │ 🟢 Efficient       │  │
│     └───────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

**AI/LLM Improvement Actions**:
| Insight | Action | Scout Deep Dive |
|---------|--------|-----------------|
| High tokens, moderate quality | Compress system prompt, remove redundancy | traceX: compare high vs low token traces |
| Quality plateau at token count | Find optimal prompt length | traceX: sample traces at different token levels |
| Agent has low quality/token ratio | Review and rewrite prompt template | traceX: examine low-scoring generations |

---

### Dashboard 8: Model A/B Comparison

**Purpose**: Compare model performance for optimization decisions

**Scout Integration**: traceX side-by-side trace comparison

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Model A/B Comparison                                     [Time Range]       │
├─────────────────────────────────────────────────────────────────────────────┤
│ FILTERS: [Model A: claude-sonnet ▼] [Model B: gemini-3-flash ▼]             │
├────────────────────────────────────────────────────────────────────────────┤
│ ROW: Head-to-Head Comparison                                                │
├─────────────────────────────────────────────────────────────────────────────┤
│     COMPARISON TABLE                                                        │
│     ┌───────────────────────────────────────────────────────────────────┐  │
│     │ Metric              │ claude-sonnet │ gemini-3-flash │ Winner    │  │
│     ├─────────────────────┼───────────────┼────────────────┼───────────┤  │
│     │ Avg Quality Score   │      82       │      78        │ 🏆 Claude │  │
│     │ Pass Rate           │      91%      │      85%       │ 🏆 Claude │  │
│     │ Avg Latency         │     2.8s      │     1.2s       │ 🏆 Gemini │  │
│     │ Cost per Request    │    $0.012     │    $0.003      │ 🏆 Gemini │  │
│     │ Cost per Quality Pt │   $0.00015    │   $0.00004     │ 🏆 Gemini │  │
│     │ Error Rate          │     1.2%      │     2.8%       │ 🏆 Claude │  │
│     └───────────────────────────────────────────────────────────────────┘  │
│     → [Compare traces side-by-side in traceX]                               │
├────────────────────────────────────────────────────────────────────────────┤
│ ROW: Performance Over Time                                                  │
├────────────────────────────────────┬────────────────────────────────────────┤
│     TIME SERIES                    │      TIME SERIES                       │
│     Quality Score Trend            │      Latency Trend                     │
│     ┌────────────────────┐         │      ┌────────────────────┐           │
│     │ ── claude          │         │      │ ── claude          │           │
│     │ ─ ─ gemini         │         │      │ ─ ─ gemini         │           │
│     └────────────────────┘         │      └────────────────────┘           │
├────────────────────────────────────┴────────────────────────────────────────┤
│ ROW: Quality Distribution Comparison                                        │
├────────────────────────────────────┬────────────────────────────────────────┤
│     HISTOGRAM (Overlay)            │      BOX PLOT                         │
│     Score Distribution             │      Latency Distribution              │
│     ┌────────────────────┐         │      ┌────────────────────┐           │
│     │    ▓▓              │         │      │ claude  ├──[███]──┤│           │
│     │   ▓▓░░             │         │      │ gemini  ├[██]─┤    │           │
│     │  ▓▓▓░░░            │         │      │         0    2    4s│           │
│     │ ▓=claude ░=gemini  │         │      └────────────────────┘           │
│     └────────────────────┘         │      → [Click outliers → traceX]      │
├────────────────────────────────────┴────────────────────────────────────────┤
│ ROW: Recommendation Engine                                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│     RECOMMENDATION PANEL                                                    │
│     ┌───────────────────────────────────────────────────────────────────┐  │
│     │ 📊 Based on your data:                                            │  │
│     │                                                                   │  │
│     │ • For HIGH-QUALITY campaigns: Use claude-sonnet                   │  │
│     │   (+4 quality points, 91% pass rate)                              │  │
│     │                                                                   │  │
│     │ • For COST-SENSITIVE campaigns: Use gemini-3-flash               │  │
│     │   (75% cost reduction, acceptable 85% pass rate)                  │  │
│     │                                                                   │  │
│     │ • For LOW-LATENCY needs: Use gemini-3-flash                       │  │
│     │   (2.3x faster response time)                                     │  │
│     │                                                                   │  │
│     │ → [View sample traces for each recommendation in traceX]          │  │
│     └───────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

**AI/LLM Improvement Actions**:
| Insight | Action | Scout Deep Dive |
|---------|--------|-----------------|
| Model A better quality, Model B cheaper | Route by campaign priority | traceX: compare quality at similar prompts |
| One model has higher error rate | Investigate error types | logX: filter errors by model |
| Latency variance high on one model | Check for retry patterns | traceX: examine p99 latency traces |

---

### Dashboard 9: Database Impact on LLM Pipeline

**Purpose**: Understand how database performance affects AI pipeline

**Scout Integration**: Direct links to pgX for query analysis

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Database Impact on LLM Pipeline                          [Time Range]       │
├─────────────────────────────────────────────────────────────────────────────┤
│ ROW: DB Health vs Pipeline Health                                           │
├────────────┬────────────┬────────────┬────────────┬────────────────────────┤
│   STAT     │   STAT     │   STAT     │   GAUGE    │      CORRELATION       │
│   DB Avg   │   Pipeline │   DB       │   Pool     │      DB↔Pipeline       │
│   Latency  │   Avg Time │   Queries  │   Usage    │      ┌──────────┐     │
│   8.2ms    │   4.2s     │   15.6K    │   24/100   │      │ r = 0.72 │     │
│            │            │            │            │      └──────────┘     │
├────────────┴────────────┴────────────┴────────────┴────────────────────────┤
│ ROW: Correlation Analysis                                                   │
├────────────────────────────────────┬────────────────────────────────────────┤
│     DUAL-AXIS TIME SERIES          │      SCATTER PLOT                     │
│     DB Latency vs Pipeline Latency │      DB Time vs Total Pipeline Time   │
│     ┌────────────────────┐         │      ┌────────────────────┐           │
│     │ ── db_latency      │         │      │      · · ·         │           │
│     │ ─ ─ pipeline_time  │         │      │    · · · ·         │           │
│     │ (notice correlation)│         │      │  · · ·             │           │
│     └────────────────────┘         │      └────────────────────┘           │
│     → [Zoom to spike → pgX]        │      → [Click outlier → full trace]   │
├────────────────────────────────────┴────────────────────────────────────────┤
│ ROW: Query Impact by Agent                                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│     TABLE                                                                   │
│     Database Operations per Agent                                           │
│     ┌───────────────────────────────────────────────────────────────────┐  │
│     │ Agent      │ Queries │ Avg DB ms │ % of Pipeline │ Top Query     │  │
│     │ research   │   3.2   │   12ms    │     0.5%      │ SELECT camp.. │  │
│     │            │         │           │               │ → [pgX]       │  │
│     │ generate   │   2.1   │   45ms    │     1.4%      │ INSERT email..│  │
│     │            │         │           │               │ → [pgX]       │  │
│     │ evaluate   │   1.5   │   8ms     │     0.8%      │ UPDATE camp.. │  │
│     └───────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

**AI/LLM Improvement Actions**:
| Insight | Action | Scout Deep Dive |
|---------|--------|-----------------|
| DB latency correlates with pipeline slowness | Optimize queries or add indexes | pgX: identify slow queries |
| High query count per agent | Batch operations, reduce N+1 | traceX: see query pattern in trace |
| Vector search slow | Tune HNSW parameters, add more memory | pgX: vector index analysis |

---

### Dashboard 10: End-to-End Latency Breakdown

**Purpose**: Understand where time is spent in the pipeline

**Scout Integration**: Click any segment to drill into traceX

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ End-to-End Latency Breakdown                             [Time Range]       │
├─────────────────────────────────────────────────────────────────────────────┤
│ ROW: Time Distribution                                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│     STACKED BAR (100%)                                                      │
│     Where Time Goes (Average Pipeline)                                      │
│     ┌───────────────────────────────────────────────────────────────────┐  │
│     │ ▓▓▓▓▓▓▓▓▓▓▓▓░░░░░░▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒░░░░░░░░░░░░  │  │
│     │ │ research │ person │      generate           │  evaluate  │       │  │
│     │ │   18%    │  12%   │        52%              │    18%     │       │  │
│     │                                                                    │  │
│     │ Breakdown of "generate" (52% of total):                            │  │
│     │ ├─ LLM API call: 45%                                               │  │
│     │ ├─ Response parsing: 4%                                            │  │
│     │ └─ DB write: 3%                                                    │  │
│     └───────────────────────────────────────────────────────────────────┘  │
│     → [Click segment to view representative trace in traceX]                │
├────────────────────────────────────────────────────────────────────────────┤
│ ROW: Latency Trends by Component                                            │
├────────────────────────────────────┬────────────────────────────────────────┤
│     TIME SERIES (Stacked Area)     │      TIME SERIES (Lines)              │
│     Absolute Time by Component     │      LLM vs Non-LLM Time              │
│     ┌────────────────────┐         │      ┌────────────────────┐           │
│     │ ▓▓▓▓▓▓▓▓▓▓ generate│         │      │ ── LLM time (85%)  │           │
│     │ ░░░░░░░░░░ research│         │      │ ─ ─ Other (15%)    │           │
│     │ ▒▒▒▒▒▒▒▒▒▒ other   │         │      └────────────────────┘           │
│     └────────────────────┘         │      → Optimization focus: LLM calls  │
├────────────────────────────────────┴────────────────────────────────────────┤
│ ROW: Latency by Percentile                                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│     GROUPED BAR CHART                                                       │
│     p50 / p90 / p99 by Component                                            │
│     ┌───────────────────────────────────────────────────────────────────┐  │
│     │           p50        p90        p99                                │  │
│     │ research  ▓▓▓░░░░░░  (1.2s)    (2.1s)    (5.4s)                   │  │
│     │ generate  ▓▓▓▓▓▓▓▓░░░░░░░░░░░  (2.8s)    (4.5s)    (12.1s) ⚠️     │  │
│     │ evaluate  ▓▓░░░░░░   (0.8s)    (1.2s)    (2.8s)                   │  │
│     │                                                                    │  │
│     │ ⚠️ High p99 variance on generate - investigate outliers            │  │
│     └───────────────────────────────────────────────────────────────────┘  │
│     → [View p99 traces in traceX]                                           │
├────────────────────────────────────────────────────────────────────────────┤
│ ROW: Optimization Opportunities                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│     INSIGHTS PANEL                                                          │
│     ┌───────────────────────────────────────────────────────────────────┐  │
│     │ 🎯 Optimization Priorities (by impact):                           │  │
│     │                                                                   │  │
│     │ 1. GENERATE agent LLM calls (52% of time)                         │  │
│     │    - Consider: shorter prompts, faster model, streaming           │  │
│     │    → [Analyze generate traces in traceX]                          │  │
│     │                                                                   │  │
│     │ 2. RESEARCH agent (18% of time, high variance)                    │  │
│     │    - Consider: caching, parallel lookups                          │  │
│     │    → [View research span patterns in traceX]                      │  │
│     │                                                                   │  │
│     │ 3. DB operations (3% but affects tail latency)                    │  │
│     │    - Consider: connection pooling, query optimization             │  │
│     │    → [Analyze in pgX]                                             │  │
│     └───────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

### Dashboard 11: Business ROI & Campaign Intelligence

**Purpose**: Connect AI metrics to business outcomes

**Scout Integration**: Drill into campaign traces for debugging

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Business ROI & Campaign Intelligence                     [Time Range]       │
├─────────────────────────────────────────────────────────────────────────────┤
│ ROW: Business KPIs                                                          │
├────────────┬────────────┬────────────┬────────────┬────────────────────────┤
│   STAT     │   STAT     │   STAT     │   STAT     │      TREND             │
│   Campaigns│   Emails   │   Cost per │   Quality  │      ROI Trend         │
│   Completed│   Generated│   Email    │   Rate     │      ┌──────────┐     │
│   234      │   1,872    │   $0.023   │   87%      │      │  ↗       │     │
│            │            │            │            │      └──────────┘     │
├────────────┴────────────┴────────────┴────────────┴────────────────────────┤
│ ROW: Campaign Performance Matrix                                            │
├─────────────────────────────────────────────────────────────────────────────┤
│     HEATMAP TABLE                                                           │
│     Campaign Performance Overview                                           │
│     ┌───────────────────────────────────────────────────────────────────┐  │
│     │ Campaign  │ Emails │ Quality │ Cost   │ Time   │ Status         │  │
│     │ camp-001  │   45   │ ▓▓▓▓▓92%│ $1.04  │  4.2m  │ ✅ Excellent   │  │
│     │           │        │         │        │        │ → [traceX]     │  │
│     │ camp-002  │   38   │ ▓▓▓░░68%│ $0.89  │  3.8m  │ ⚠️ Review      │  │
│     │           │        │         │        │        │ → [traceX]     │  │
│     │ camp-003  │   52   │ ▓▓▓▓░85%│ $1.21  │  5.1m  │ ✅ Good        │  │
│     └───────────────────────────────────────────────────────────────────┘  │
│     → Click any campaign to see all traces in traceX                        │
├────────────────────────────────────────────────────────────────────────────┤
│ ROW: Cost Efficiency Analysis                                               │
├────────────────────────────────────┬────────────────────────────────────────┤
│     SCATTER PLOT                   │      QUADRANT CHART                   │
│     Quality vs Cost per Email      │      Campaign Segmentation            │
│     ┌────────────────────┐         │      ┌────────────────────┐           │
│     │    · camp-001      │         │      │ High Q │ ⭐     │ 🎯     │     │
│     │  · camp-003        │         │      │ Low Q  │ ❌     │ 💰     │     │
│     │      · camp-002    │         │      │        │ High $ │ Low $  │     │
│     │  Quality ↑ Cost →  │         │      └────────────────────┘           │
│     └────────────────────┘         │      ⭐=Optimize 🎯=Ideal             │
│     → [Click to investigate]       │      ❌=Fix 💰=Scale                   │
├────────────────────────────────────┴────────────────────────────────────────┤
│ ROW: Improvement Recommendations                                            │
├─────────────────────────────────────────────────────────────────────────────┤
│     ACTIONABLE INSIGHTS                                                     │
│     ┌───────────────────────────────────────────────────────────────────┐  │
│     │ 📈 Improvement Opportunities:                                     │  │
│     │                                                                   │  │
│     │ 🔴 camp-002: Quality below threshold (68%)                        │  │
│     │    Root cause: 12 emails failed evaluation on "relevance"         │  │
│     │    → [View failed evaluations in traceX]                          │  │
│     │    → [Check evaluation logs in logX]                              │  │
│     │                                                                   │  │
│     │ 🟡 camp-001: High cost ($1.04/email vs avg $0.89)                 │  │
│     │    Root cause: Using claude-sonnet, could use gemini for some     │  │
│     │    → [Compare model performance in traceX]                        │  │
│     │                                                                   │  │
│     │ 🟢 camp-003: Good candidate for scaling                           │  │
│     │    85% quality at reasonable cost - replicate this pattern        │  │
│     │    → [Analyze successful pattern in traceX]                       │  │
│     └───────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Dashboard-to-Scout Integration Patterns

### Deep Link Patterns

Every dashboard should include **clickable deep links** to Scout explorers:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Integration Pattern: Dashboard → Scout Explorer                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│ 1. METRIC CLICK → traceX                                                   │
│    Dashboard stat shows "23 errors"                                         │
│    Click → Opens traceX with filter: status=ERROR                          │
│                                                                             │
│ 2. TIME RANGE SELECTION → All Explorers                                    │
│    Drag-select spike on dashboard chart                                     │
│    Click "Investigate" → Opens traceX/logX with same time range            │
│                                                                             │
│ 3. TABLE ROW → Contextual Explorer                                         │
│    Click campaign row → traceX with campaign_id filter                     │
│    Click slow query → pgX with query filter                                │
│    Click error type → logX with error filter                               │
│                                                                             │
│ 4. ANNOTATION → Correlated View                                            │
│    Deployment annotation on dashboard                                       │
│    Click → See traces/logs before and after deployment                     │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Scout Query Templates

Pre-built queries to embed in dashboard links:

| Dashboard Context | traceX Query | logX Query | pgX Query |
|-------------------|--------------|------------|-----------|
| Error investigation | `status=ERROR AND gen_ai.agent.name={agent}` | `level:ERROR AND agent:{agent}` | - |
| Slow requests | `duration>5s AND gen_ai.operation.name=chat` | - | `duration>100ms` |
| Campaign debug | `campaign_id={id}` | `campaign_id:{id}` | - |
| Quality failures | `gen_ai.evaluation.score.label=failed` | `"evaluation failed"` | - |
| Cost anomaly | `gen_ai.usage.cost_usd>0.05` | - | - |
| DB bottleneck | `db.system=postgresql AND duration>50ms` | - | `avg_time>50ms` |

---

## Continuous Improvement Workflow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│              AI/LLM Continuous Improvement Cycle                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│    ┌──────────────┐                                                        │
│    │  DASHBOARDS  │ ◄─────────────────────────────────────────┐            │
│    │  (Metrics)   │                                           │            │
│    └──────┬───────┘                                           │            │
│           │ Alert / Anomaly detected                          │            │
│           ▼                                                   │            │
│    ┌──────────────┐                                           │            │
│    │   traceX     │ Investigate individual requests           │            │
│    │   (Traces)   │ Compare fast vs slow, success vs fail     │            │
│    └──────┬───────┘                                           │            │
│           │ Need more context                                 │            │
│           ▼                                                   │            │
│    ┌──────────────┐                                           │            │
│    │    logX      │ Find error patterns, warnings             │            │
│    │   (Logs)     │ Correlate with trace timeline             │            │
│    └──────┬───────┘                                           │            │
│           │ DB-related issue?                                 │            │
│           ▼                                                   │            │
│    ┌──────────────┐                                           │            │
│    │    pgX       │ Analyze query performance                 │            │
│    │ (PostgreSQL) │ Check connection pool, indexes            │  Measure   │
│    └──────┬───────┘                                           │  Impact    │
│           │                                                   │            │
│           ▼                                                   │            │
│    ┌──────────────┐                                           │            │
│    │   IMPROVE    │ Optimize prompt, switch model,            │            │
│    │   (Action)   │ tune DB, fix code                         │            │
│    └──────┬───────┘                                           │            │
│           │                                                   │            │
│           └───────────────────────────────────────────────────┘            │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Improvement Categories

| Category | Dashboard Signal | Scout Investigation | Typical Fix |
|----------|------------------|---------------------|-------------|
| **Quality** | Pass rate drops | traceX: failed evaluations | Improve prompts |
| **Cost** | Spend spike | traceX: high-token requests | Compress prompts, switch model |
| **Latency** | p99 increases | traceX + pgX: bottleneck | Optimize queries, cache |
| **Reliability** | Error rate up | logX: error patterns | Add retries, fix bugs |
| **Efficiency** | Low quality/token | traceX: compare good vs bad | Prompt engineering |
