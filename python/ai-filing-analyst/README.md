# AI Filing Analyst

A service that answers questions about a US-listed company's reported financials, with local Ollama models. The same
service runs on one of four agent frameworks, picked by `FILING_FRAMEWORK`: Strands Agents (the default), Google ADK,
Microsoft Agent Framework or the OpenAI Agents SDK. An analyst agent looks up figures, computes ratios and, for a
ranking question, calls a second agent that places the company among every filer of a concept. Every figure in an answer
is a fact the company filed with the SEC, cited by the accession number of the filing it came from, and a verifier
checks that before the answer is served. The data comes from the SEC's XBRL APIs, which need no key. Each question is
one trace, with trace-correlated logs and application metrics exported to base14 Scout.

**Stack**: Python 3.14 · FastAPI 0.141 · Strands Agents 1.57, Google ADK 2.10, Microsoft Agent Framework 1.19 or
OpenAI Agents SDK 0.22 · PostgreSQL 18 · Ollama (local models) · OpenTelemetry SDK 1.45 (1.42 with ADK) · base14 Scout

One of the [Python examples](../README.md) in base14's [OpenTelemetry examples](../../README.md) repository. For a
durable agent on Temporal, read [ai-kyc-onboarding](../ai-kyc-onboarding) (Pydantic AI). Other links are under
[References](#references).

## How to instrument the agent with OpenTelemetry

The shared part lives in `src/filing_analyst/telemetry.py`. `main.py` calls `configure_telemetry` at startup, before
the framework is loaded.

1. Install `opentelemetry-sdk`, the OTLP HTTP exporter and the FastAPI, psycopg, httpx and logging
   instrumentations, as pinned in `pyproject.toml`, plus the framework's extra.
2. Build a `TracerProvider` with a `BatchSpanProcessor` around the OTLP span exporter, and a `MeterProvider` with a
   `PeriodicExportingMetricReader` around the OTLP metric exporter. Set both as the global providers. Every
   framework here reads the global providers, so its spans and metrics carry this resource.
3. Build a `LoggerProvider` with the OTLP log exporter and add a `LoggingHandler` for it to the root logger. Every
   record then carries the trace ID and span ID of the span it was written under.
4. Set `OTEL_SERVICE_NAME`, `OTEL_EXPORTER_OTLP_ENDPOINT` and the other standard variables as `.env.example` and
   `compose.yaml` ship them. The resource also carries `base14.filing.framework`, the framework in use.

Each adapter in `src/filing_analyst/frameworks/` then does what its framework needs.

### Strands Agents

- Install `strands-agents[otel,ollama]`. `StrandsTelemetry` is not used, because it installs a meter provider with
  its own resource.
- Build each `Agent` per request and pass `trace_attributes`. Strands copies them onto every span of that agent's
  run, which is how the question ID and ticker reach `invoke_agent`, `chat` and `execute_tool`. Strands applies them
  after its own attributes, so the adapter also sets `gen_ai.provider.name` to `ollama` and adds `server.address` and
  `server.port` there.
- Set `OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental` so Strands emits the current GenAI semantic
  conventions. Strands reads it once, when its tracer is first built.

### Google ADK

- Install `google-adk`, which reaches Ollama through LiteLLM with the `ollama_chat/` model prefix. ADK caps
  OpenTelemetry at 1.42, so this extra pins the SDK at 1.42.1 and the instrumentations at 0.63b1.
- ADK emits its spans and `gen_ai.*` metrics through the global providers with no setup.
- ADK has no per-agent trace attributes. `AgentRunAttributesProcessor` in `telemetry.py` adds the question's
  attributes to each GenAI span as it starts, from a context variable the adapter sets around the run.
- The session ID is the question ID, which ADK records as `gen_ai.conversation.id`.

### Microsoft Agent Framework

- Install `agent-framework-core` and `agent-framework-ollama`.
- Call `enable_instrumentation` once at startup. `enable_sensitive_data` follows
  `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT`.
- `AgentRunAttributesProcessor` adds the question's attributes, as for ADK.

### OpenAI Agents SDK

- Install `openai-agents`, `opentelemetry-instrumentation-genai-openai-agents` and
  `opentelemetry-instrumentation-genai-openai`. The models reach Ollama through its OpenAI-compatible `/v1` endpoint.
- Call `OpenAIAgentsInstrumentor().instrument(disable_openai_trace_export=True)`. It replaces the SDK's trace
  processors with its own, so the SDK's exporter to OpenAI is removed. `OpenAIInstrumentor().instrument()` adds the
  model-call spans.
- The model-call spans report the provider as `openai`. The exporter in `telemetry.py` sets `gen_ai.provider.name` to
  `ollama` on every model-call span, for every framework.
- `AgentRunAttributesProcessor` adds the question's attributes, as for ADK.

## Prerequisites

- Python 3.14 and [uv](https://docs.astral.sh/uv/), for the checks, the tests and `scripts/verify-scout.sh`.
- Docker and Docker Compose.
- `curl` and `jq`, for the quick start and the scenario harness.
- Ollama on the host, with both models pulled: `ollama pull qwen3.5:9B` and `ollama pull gemma4:e2b`.
- A name and contact email for the SEC User-Agent. See [SEC data](#sec-data).
- base14 Scout credentials, optional. Without them the collector still starts and prints everything through its
  `debug` exporter, but every send to Scout fails and the collector logs the errors. See [Scout export](#scout-export).

No LLM provider key is needed. Every model call goes to Ollama.

## Quick start

```bash
cp .env.example .env
ollama pull qwen3.5:9B
ollama pull gemma4:e2b
make docker-up
```

Set `SEC_USER_AGENT` in `.env` to your organisation's name and a contact email, such as
`Acme Research ops@acme.example`. The API refuses to start without it. Fill in the `SCOUT_*` variables, or export them
in your shell, to export to Scout.

This starts Postgres, the collector and the `api` service on port 8000. Postgres is on host port 5433. At startup the
API loads the SEC ticker list into Postgres and reads each model's digest from Ollama.

To run on another framework, set `FILING_FRAMEWORK` to `adk`, `maf` or `openai-agents` in `.env`, or pass it to
`make docker-up`, and rebuild. The image installs that framework only.

```bash
make docker-up FRAMEWORK=adk
curl -s http://localhost:8000/health | jq .framework
```

Ask a question:

```bash
curl -s -X POST http://localhost:8000/questions \
  -H 'Content-Type: application/json' \
  -d '{"ticker": "KVYO", "question": "What was Klaviyo'"'"'s revenue for its latest fiscal year?"}' | jq
```

```json
{
  "question_id": "q-576d029d51ad",
  "ticker": "KVYO",
  "company": "Klaviyo, Inc.",
  "outcome": "answered",
  "answer": "Klaviyo's revenue for its latest fiscal year (2025) was $1,234.0 million.",
  "figures": [
    {
      "concept": "RevenueFromContractWithCustomerExcludingAssessedTax",
      "value": 1234019000.0,
      "unit": "USD",
      "fiscal_year": 2025,
      "form": "10-K",
      "accession": "0001835830-26-000007"
    }
  ],
  "ratios": [],
  "caveats": [],
  "rankings": [],
  "citations_verified": 1,
  "facts_source": "stored",
  "sec_calls": 0
}
```

`question_id` is on every span and log line of the question. `facts_source` says where the company's facts came
from for this question: `cache` for the shipped files, `sec` for a live fetch, `stored` when an earlier question
loaded them. Check a figure against what is stored:

```bash
curl -s "http://localhost:8000/companies/KVYO/facts?concept=revenue" | jq '.rows[0]'
```

`make docker-down` stops the stack and deletes the Postgres volume, which holds the loaded facts.

## How a question runs

1. The API resolves the ticker in Postgres. An unknown ticker gets a 404 before any model call.
2. If the company has no facts stored, the API loads them under the server span, before the agent starts: from the
   shipped cache for the seven companies in it, otherwise from the SEC. A Postgres advisory lock per company makes two
   first questions on one company load it once.
3. The API builds the analyst agent for this request and runs it under a call budget and a wall-clock budget.
4. The analyst calls its tools:
   - `query_facts` returns up to twelve annual rows for one concept, each with value, unit, period, fiscal year, form
     and accession number.
   - `compute_ratio` computes one of six ratios in Python from stored facts: `net_margin`, `operating_margin`,
     `gross_margin`, `revenue_growth`, `current_ratio` and `liabilities_to_assets`. The model never does the
     arithmetic.
   - `rank_among_filers` is the ranking agent, attached with the framework's agent-as-tool (`as_tool` in Strands, MAF
     and OpenAI Agents, `AgentTool` in ADK). It runs on the smaller model with one tool, `frame_values`, which
     fetches one SEC frame and returns the company's value and rank, the filer count, the median and the five
     largest filers.
5. The analyst returns a typed `FilingAnswer` by calling an answer tool: Strands' `structured_output_model`, ADK's
   `set_model_response` from `output_schema`, and a `FilingAnswer` function tool on MAF and OpenAI Agents. A run that
   ends in text on MAF or OpenAI Agents gets one reminder to call it, as Strands does.
6. The verifier checks the answer against the tool results of this run: every figure must have come back from a tool
   with the same fiscal year and accession number, and every number in the answer text must be in the figures. An
   answer that fails is not served.

A hook on the ranking tool settles what the analyst reads from the ranking agent, whatever the smaller model wrote.
When the frame placed the company, the hook appends the frame's facts as `frame_values` returned them: the frame,
what it admits, the rank, the filer count, the value and the accession number. When the frames fetch fails, it
replaces the reply with a fixed line saying the ranking is unavailable. The API adds a caveat for either case: which
frame the ranking is among, or that the ranking is unavailable.

The two budgets are per question. The call budget counts model and tool calls across both agents, `CALL_BUDGET` in
total, through the framework's hooks: Strands hooks, ADK callbacks, MAF middleware and OpenAI Agents run hooks. The
wall-clock budget, `QUESTION_TIMEOUT_SECONDS`, sets Strands' `cancel_signal`, which Strands reads between stream
chunks, cycles and tools, so a model call or tool that stalls is cancelled outright two seconds later. The other
adapters cancel the run task at the deadline.

## Endpoints

| Method and path | Work | Responses |
| --- | --- | --- |
| `POST /questions` | Run the analyst for one question. | 200 with the answer. 404 unknown ticker. 422 malformed body, over-long question, or `fault`, `call_budget` or `timeout_seconds` while `FILING_FAULTS_ENABLED` is not `true`. 502 model or SEC failure, bad output or ungrounded answer. 503 inside an SEC back-off. 504 budget or timeout. 500 any other failure, such as Postgres down. |
| `GET /companies/{ticker}/facts?concept=` | Read stored facts for one concept, for checking an answer by hand. | 200. 404 unknown ticker or no facts stored. 422 unknown concept. |
| `GET /health` | Postgres, the stored fact count and the fixture date. | 200. 503 when Postgres is down. |

A refusal carries `reason` and `detail`. The `reason` values are `unknown_ticker`, `faults_disabled`,
`unknown_fault`, `question_too_long`, `sec_unavailable`, `sec_backoff`, `model_unavailable`, `bad_output`,
`run_failed`, `ungrounded`, `budget`, `timeout` and `internal`.

## Scenarios

`scripts/test-api.sh` drives seventeen scenarios against the running stack and checks each answer's status,
outcome, figures and accession numbers. Eight of them inject a failure, so start the stack with faults enabled:

```bash
FILING_FAULTS_ENABLED=true docker compose up -d --build
scripts/test-api.sh                     # all seventeen
scripts/test-api.sh ranking bad_output  # a subset
```

The harness empties the `facts` table first, so every first question loads its company. Results and question IDs go
to `.harness/last-run.json`.

| Scenario | Question | Fault | Outcome | What to look for in the trace |
| --- | --- | --- | --- | --- |
| `unknown_ticker` | `ZZZZQ`, revenue. | None | 404 `rejected` | No agent span, a WARN `Unknown ticker` line. |
| `single_figure` | `KVYO`, latest revenue. | None | `answered` | Facts loaded from the cache under the server span, then `invoke_agent analyst` and `filing.verify_answer`. |
| `ratio` | `FRSH`, latest net margin. | None | `answered` | `execute_tool compute_ratio`, and two figures with their accession numbers. |
| `second_question` | `FRSH` again, latest revenue. | None | `answered` | No SEC client span and no facts load. |
| `trend` | `WK`, revenue for three years. | None | `answered` | Three figures, checked against the three latest years stored. |
| `restated` | `WK`, net income for 2019. | None | `answered` | The value and accession number of the latest filing that reported it. See [SEC data](#sec-data). |
| `ranking` | `ABNB`, net income rank for 2025. | None | `answered` | `invoke_agent ranking` under `execute_tool rank_among_filers`, and a `GET` frames span under `execute_tool frame_values`. |
| `outside_cache` | `KLTR`, latest revenue. | None | `answered` | A `GET` companyfacts span under the server span, then a normal answer. |
| `not_in_data` | `AMPL`, headcount by region. | None | `not_available` | A WARN line that the concept resolved to no facts, and no figure. |
| `sec_down` | `YEXT`, latest revenue. | The first two SEC attempts fail. | `answered` | Two error `GET` spans, two WARN retry lines, then a successful attempt. |
| `sec_unreachable` | `ABNB`, net income rank. | Every frames attempt fails. | `not_available` | `execute_tool frame_values` with error status under the ranking agent, while `invoke_agent analyst` keeps running. The answer says the ranking is unavailable. |
| `timeout` | `WK`, latest revenue. | The model stalls; a 5 second budget. | 504 `timeout` | `invoke_agent analyst` ended by the cancel signal without error status, and a WARN budget line. |
| `ungrounded_answer` | `WK`, net income for 2019. | The answer cites an invented accession number. | 502 `ungrounded` | `filing.verify_answer` with `base14.filing.rejection_reason`. |
| `model_unavailable` | `WK`, latest revenue. | The first model call fails to connect. | 502 `error` | Error `chat` and `invoke_agent` spans, and an ERROR line. |
| `tight_budget` | `FRSH`, latest net margin. | A call budget of 3. | 504 `budget` | `invoke_agent analyst` with `error.type` `filing_analyst.budget.BudgetExceeded`. |
| `bad_output` | `WK`, latest revenue. | The first answer fails validation, then the model stops calling the answer tool. | 502 `error` | One `execute_tool FilingAnswer` span with error status and a WARN retry line. |
| `sec_blocked` | `BOX`, then `ASAN`. | The SEC answers 403, with a 20 second back-off. | 502, then 503 `sec_backoff` | One 403 `GET` span and no retry. The second question has no client span. |

A fault is chosen per question in the `fault` field of `POST /questions`. `sec_blocked` runs last, because the
back-off refuses every new company until it ends.

The trace column describes Strands. The other frameworks differ in two scenarios. `model_unavailable` raises in the
framework's hook before the model call, so ADK has an error `call_llm` span with no `generate_content` child, and MAF
and OpenAI Agents have no model span, only the error `invoke_agent`. For `bad_output`,
the answer tool succeeds and the rewritten answer fails validation after the run, with a WARN validation line. On
OpenAI Agents, a budget stop that turns the answer tool away lands on the reminder run's `invoke_agent analyst`.

Then check the telemetry the run produced:

```bash
scripts/verify-scout.sh
scripts/verify-scout.sh --allow-partial   # after running a subset
```

It reads the collector's `debug` output and self-metrics for the run and checks, per question: one trace under
`POST /questions` with the outcome the harness saw, `error.type` on every span with error status, every log line on
an exported span and carrying the question ID, both agents nested as described below with the trace attributes on
every GenAI span, tokens and cost on each completed model span, and each scenario's failure shape. It reads the
framework from the run file and checks that framework's span names and metrics. It also checks that every
application and framework metric has data points, and that the Scout exporter sent spans, log records and
metric points with no failures. Do not restart the collector between the run and the verification, since its
self-metrics reset on restart.

## Telemetry

The API exports traces, metrics and logs over OTLP HTTP to the collector, as the service `ai-filing-analyst`. Each
process gets a fresh `service.instance.id`.

The resource carries `base14.filing.framework`, so runs on different frameworks can be told apart in Scout.

### The trace of one question

This is the ranking question on Strands. The psycopg `SELECT` and `INSERT` spans and the ASGI `http receive` and
`http send` spans are elided.

```text
POST /questions                                base14.filing.question_id, ticker, outcome, sec_calls
|-- invoke_agent analyst                       qwen3.5:9B
|   |-- execute_event_loop_cycle
|   |   |-- chat
|   |   `-- execute_tool rank_among_filers
|   |       `-- invoke_agent ranking           gemma4:e2b
|   |           |-- execute_event_loop_cycle
|   |           |   |-- chat
|   |           |   `-- execute_tool frame_values
|   |           |       `-- GET                base14.sec.endpoint=frames
|   |           `-- execute_event_loop_cycle
|   |               `-- chat
|   `-- execute_event_loop_cycle
|       |-- chat
|       `-- execute_tool FilingAnswer          the typed answer
`-- filing.verify_answer
```

The models decide the tool calls, so the shape varies between runs. The analyst may also call `query_facts` for the
company's own figure, which adds a cycle with `chat` and `execute_tool query_facts`.

On a company's first question the facts load sits under `POST /questions`, before `invoke_agent analyst`: a `GET`
companyfacts span when the facts come from the SEC, and the psycopg spans of the upsert either way.

The same question on the other frameworks:

```text
Google ADK                                     Microsoft Agent Framework
POST /questions                                POST /questions
|-- invocation                                 |-- invoke_agent analyst
|   `-- invoke_agent analyst                   |   |-- chat qwen3.5:9B
|       |-- call_llm                           |   |-- execute_tool rank_among_filers
|       |   `-- generate_content ...           |   |   `-- invoke_agent ranking
|       |-- execute_tool rank_among_filers     |   |       |-- chat gemma4:e2b
|       |   `-- invocation                     |   |       `-- execute_tool frame_values
|       |       `-- invoke_agent ranking       |   |-- chat qwen3.5:9B
|       |           |-- call_llm               |   `-- execute_tool FilingAnswer
|       |           `-- execute_tool frame_... `-- filing.verify_answer
|       `-- execute_tool set_model_response
`-- filing.verify_answer

OpenAI Agents SDK
POST /questions
|-- invoke_workflow Agent workflow
|   `-- invoke_agent analyst
|       |-- chat qwen3.5:9B
|       |-- execute_tool rank_among_filers
|       |   `-- invoke_agent ranking
|       |       |-- chat gemma4:e2b
|       |       `-- execute_tool frame_values
|       |-- chat qwen3.5:9B
|       `-- execute_tool FilingAnswer
`-- filing.verify_answer
```

ADK names its model spans `generate_content ollama_chat/<model>`, after the LiteLLM route. On MAF and OpenAI Agents
an analyst run that ends in text gets one reminder to call `FilingAnswer`, which adds a second `invoke_agent analyst`
(on OpenAI Agents, a second `invoke_workflow`) under the server span.

### Hand-written spans

One, `filing.verify_answer`, around the verifier. Strands, FastAPI, httpx and psycopg cover every other step.

### Attributes this example adds

All under `base14.`, since semconv owns `gen_ai.*`.

| Span | Attributes |
| --- | --- |
| `POST /questions` | `base14.filing.question_id`, `base14.filing.ticker`, `base14.filing.outcome`, `base14.filing.sec_calls`. |
| Every GenAI span of both agents | `base14.filing.question_id`, `base14.filing.ticker`, `base14.filing.cik`, `base14.filing.fixture_date`. On Strands every span also carries `gen_ai.provider.name` (`ollama`), `server.address` and `server.port` from `OLLAMA_BASE_URL`, and `gen_ai.conversation.id` set to the question ID. |
| `invoke_agent` and model spans | `base14.prompt.version`, `base14.gen_ai.model.digest`. The ranking agent carries its own prompt version and digest. On Strands every span of the agent carries them. |
| `filing.verify_answer` | `base14.filing.figure_count`, `base14.filing.citations_verified`, and `base14.filing.rejection_reason` on a rejection. |
| SEC `GET` spans | `base14.sec.endpoint` (`companyfacts` or `frames`), `base14.sec.attempt`. |
| Model spans (`chat`, `generate_content`) | `base14.gen_ai.cost`, `base14.gen_ai.cost.simulated`, and `gen_ai.provider.name` set to `ollama`. |
| Any span with error status | `error.type`. |

Strands records the exception on a failed span but sets no `error.type`, so `CostAndErrorAttributingSpanExporter` in
`telemetry.py` adds it on the way to the OTLP exporter: from the first recorded exception, then from the HTTP status
code, then `_OTHER`. A recorded exception also replaces an `_OTHER` that an instrumentation set. Strands wraps event
loop failures in `EventLoopException`, and the exporter reports the cause instead. The same exporter computes the
cost, and sets `gen_ai.provider.name` to `ollama` on model spans, since LiteLLM and the OpenAI instrumentation report
their own names.

On ADK, MAF and OpenAI Agents, `AgentRunAttributesProcessor` in `telemetry.py` adds the question's attributes to each
GenAI span as it starts. The adapter sets them in a context variable around the run, and the processor picks the
agent's prompt version and digest from the span's agent name or model.

`base14.gen_ai.model.digest` is read from Ollama at startup, because a model tag can point at new weights.
`base14.prompt.version` is the timestamp prefix of the prompt file.

### GenAI spans

Strands emits `invoke_agent <agent>` per run, `execute_event_loop_cycle` per model turn, `chat` per model call and
`execute_tool <tool>` per tool call. ADK adds `invocation` per run and `call_llm` around each model call. OpenAI
Agents adds `invoke_workflow` per run. The keys worth knowing, as Strands records them:

- `gen_ai.agent.name` is `analyst` or `ranking`, and `gen_ai.agent.tools` lists the agent's tools.
- `gen_ai.request.model` is the Ollama tag.
- `gen_ai.provider.name` is `ollama` and `server.address` and `server.port` point at it, set through
  `trace_attributes`. Strands on its own writes `strands-agents` and no server.
- `gen_ai.usage.input_tokens` and `gen_ai.usage.output_tokens` on `chat`, and the run's totals on `invoke_agent`.
- `gen_ai.tool.name`, `gen_ai.tool.call.arguments`, `gen_ai.tool.call.result` and `gen_ai.tool.status` on
  `execute_tool`.
- `gen_ai.system_instructions` on `invoke_agent`.

### Cost

`base14.gen_ai.cost` is computed from the token counts and the model's row in `_shared/pricing.json`. The local models
have no row, so their cost is 0 and `base14.gen_ai.cost.simulated` is `true`.

### Logs

Standard `logging` goes to the collector through the `LoggingHandler`. Every line carries the trace ID and span ID of
the span it was logged on, and every line written for a question carries `base14.filing.question_id`.

| Line | Level | Span |
| --- | --- | --- |
| `Question ... received for ...` | INFO | `POST /questions` |
| `Facts loaded for CIK ... from <cache or sec>: ... rows` | INFO | `POST /questions` |
| `Frame ... fetched with ... filers` | INFO | `execute_tool frame_values` |
| `Answer for question ... returned with ... figures: <outcome>` | INFO | `POST /questions` |
| `Unknown ticker ...` | WARN | `POST /questions` |
| `Concept ... resolved to no 10-K facts for CIK ...` | WARN | `execute_tool query_facts` |
| `SEC <endpoint> attempt ... failed with ...; retrying` | WARN | The server span or the tool span that made the call. |
| `SEC back-off in force; question refused for CIK ...` | WARN | `POST /questions` |
| `Structured output failed validation, retrying: ...` | WARN | `execute_tool FilingAnswer`, on Strands. |
| `Structured output failed validation: ...` | WARN | `POST /questions`, on the other frameworks. |
| `Call budget of ... spent: ...` | WARN | The call that went over. |
| `Question ... passed its ... second budget after ...` | WARN | `POST /questions` |
| `Answer rejected by the verifier: <reason>` | WARN | `POST /questions` |
| `SEC <endpoint> failed after ... attempts: ...` | ERROR | The span that made the call. |
| `SEC answered 403 on ...; back-off started` | ERROR | `POST /questions` |
| `Run failed for question ...: ...` | ERROR | `POST /questions` |

With `OTEL_PYTHON_LOG_CORRELATION=true`, the logging instrumentation also writes the trace ID and span ID into each
line in `docker compose logs api`. Those fields stay out of the exported records, which carry the trace context
already.

To go from a log line to its trace, open the trace ID on the line. To go from a trace to its logs, filter logs by the
trace ID, or by `base14.filing.question_id`.

### Application metrics

Defined in `src/filing_analyst/app_metrics.py`.

| Instrument | Type | Attributes |
| --- | --- | --- |
| `base14.filing.questions` | counter, `{question}` | `base14.filing.outcome`: `answered`, `not_available`, `ungrounded`, `budget`, `timeout`, `error` or `rejected`. |
| `base14.filing.question.duration` | histogram, seconds | `base14.filing.outcome` |
| `base14.filing.sec.requests` | counter, `{request}` | `base14.sec.endpoint`, and `http.response.status_code` or `error.type`. One per attempt. |
| `base14.filing.facts.loaded` | counter, `{fact}` | None. |
| `base14.filing.rankings` | counter, `{ranking}` | `base14.filing.outcome` |

### Framework metrics

Each framework records its own metrics through the global meter provider:

| Framework | Metrics |
| --- | --- |
| Strands | `strands.event_loop.cycle_count`, `strands.event_loop.start_cycle`, `strands.event_loop.end_cycle`, `strands.event_loop.cycle_duration`, `strands.event_loop.latency`, `strands.event_loop.input.tokens`, `strands.event_loop.output.tokens`, `strands.model.time_to_first_token`, `strands.tool.call_count`, `strands.tool.success_count`, `strands.tool.error_count`, `strands.tool.duration`. |
| ADK | `gen_ai.client.operation.duration`, `gen_ai.client.token.usage`, `gen_ai.execute_tool.duration`, `gen_ai.invoke_agent.duration`, `gen_ai.invoke_agent.inference_calls`, `gen_ai.invoke_agent.tool_calls`. |
| MAF | `gen_ai.client.operation.duration`, `gen_ai.client.token.usage`, `agent_framework.function.invocation.duration`. |
| OpenAI Agents | `gen_ai.client.operation.duration`, `gen_ai.client.token.usage`, `gen_ai.execute_tool.duration`, `gen_ai.invoke_agent.duration`, `gen_ai.invoke_workflow.duration`. |

The FastAPI and httpx instrumentations add `http.server.*` and `http.client.duration`.

### Content capture

`OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT` is `true` in `.env.example` and `compose.yaml`. Each framework
then records system instructions, messages, tool arguments and tool results. Token counts and the other attributes
are recorded either way.

- Strands does not read the variable. When it is `false`, `telemetry.py` appends `gen_ai_unredacted_attributes=` to
  `OTEL_SEMCONV_STABILITY_OPT_IN` before the first agent is built, which makes Strands redact all of them.
- ADK reads it for its GenAI events. Its own spans follow `ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS`, which the adapter
  sets to match.
- MAF records content only with `enable_sensitive_data`, which the adapter sets from the variable.
- The OpenAI instrumentations take a mode rather than `true`. The adapter maps `true` to `SPAN_ONLY` and `false` to
  `NO_CONTENT` before instrumenting.

`OTEL_ATTRIBUTE_VALUE_LENGTH_LIMIT` (4096) caps each attribute value, since tool results can be long.

## SEC data

The example reads three SEC XBRL APIs: the company ticker list, company facts and frames.

- **User-Agent.** The SEC asks every client to send a User-Agent with a name and contact email, and refuses requests
  without one. `SEC_USER_AGENT` sets it and the API will not start without it.
- **Rate limit.** The SEC allows ten requests a second. The client holds to `SEC_REQUESTS_PER_SECOND` (5) and makes at
  most `SEC_CALLS_PER_QUESTION` (4) calls per question.
- **Retries and back-off.** Transport errors and 5xx retry three times. A 403 is the SEC's throttle: the client stops
  the question and every SEC call fails fast without a request for `SEC_BACKOFF_SECONDS` (600).
- **Cache.** `fixtures/` holds the ticker list and the company facts of seven companies (`ABNB`, `WK`, `GTLB`, `FRSH`,
  `AMPL`, `KVYO`, `MNDY`) as fetched on the date in `fixtures/MANIFEST.json`, gzip-compressed. A question on one of
  them makes no SEC call. Any other company is fetched live. Frames are always fetched live. `make fetch-fixtures`
  refreshes the cache with the `SEC_USER_AGENT` from your shell or `.env`, and `make check-fixtures` checks the files
against
  the manifest.

How a figure is chosen, so you can check one by hand:

- Only annual facts from 10-K and 10-K/A filings are served, in USD, shares, pure and USD per share units.
- The same figure appears in several 10-Ks, sometimes restated. The latest filed value wins, as in the SEC's own
  frames API. Workiva's net income for 2019, for example, is served from its 2022 10-K.
- The fiscal year is derived from the period end, not from the filing's `fy` field, which names the filing's year
  on comparative rows.
- A frame such as `CY2025` admits every fiscal year ending in that calendar year, so a ranking is among all filers of
  the concept, not among peers. Frames carry no industry.
- `MNDY` files a 20-F, not a 10-K, so questions on it come back `not_available`.

## Scout export

The collector (`otel-collector-config.yaml`) exports every pipeline to Scout through the `otlp_http/b14` exporter,
authenticated by the `oauth2client` extension, and to the `debug` exporter. Set `SCOUT_CLIENT_ID`,
`SCOUT_CLIENT_SECRET`, `SCOUT_TOKEN_URL` and `SCOUT_ENDPOINT` in `.env` or your shell, then start or recreate the
stack. `SCOUT_ENVIRONMENT` is written as `deployment.environment.name` and `environment` on every span, log record and
data point, and defaults to `development`.

With the credentials empty, `compose.yaml` passes `unset` as the client ID and secret, so the collector starts and the
`debug` output is complete, but every send to Scout fails. `scripts/test-api.sh` still passes.
`scripts/verify-scout.sh` reports the Scout exporter checks as failed.

`scripts/verify-scout.sh` is the check that the export worked. It takes the collector's exporter counters at the end
of the run, subtracts the values `scripts/test-api.sh` recorded at its start, and passes when spans, log records and
metric points were sent to `otlp_http/b14` with none failed and no warnings or errors in the collector log.

## Configuration

`.env.example` ships these values. Compose reads `.env` when it starts the stack. The app itself reads only its
environment, so host runs take the defaults in `src/filing_analyst/config.py` unless you export the variables.

| Variable | `.env.example` | Notes |
| --- | --- | --- |
| `FILING_FRAMEWORK` | `strands` | `strands`, `adk`, `maf` or `openai-agents`. Also the Docker build argument that picks the extra to install. |
| `SEC_USER_AGENT` | a placeholder | Required. Your organisation's name and a contact email. |
| `OLLAMA_BASE_URL` | `http://host.docker.internal:11434` | Use `http://localhost:11434` on the host. |
| `ANALYST_MODEL` | `qwen3.5:9B` | The analyst agent. |
| `RANKING_MODEL` | `gemma4:e2b` | The ranking agent. |
| `OLLAMA_THINK` | `false` | Turns the models' thinking on. |
| `ANALYST_PROMPT_VERSION`, `RANKING_PROMPT_VERSION` | empty | The UTC timestamp prefix of a file under `prompts/`, such as `202609261523`. Empty uses the newest file. |
| `SEC_REQUESTS_PER_SECOND` | `5` | Below the SEC's limit of ten. |
| `SEC_BACKOFF_SECONDS` | `600` | How long a 403 stops SEC calls. |
| `SEC_CALLS_PER_QUESTION` | `4` | SEC calls one question may make. |
| `CALL_BUDGET` | `24` | Model and tool calls per question, across both agents. |
| `QUESTION_TIMEOUT_SECONDS` | `240` | Wall-clock budget per question. |
| `QUESTION_MAX_CHARS` | `500` | Longest question accepted. |
| `FILING_FAULTS_ENABLED` | `false` | `true` lets `POST /questions` take `fault`, `call_budget` and `timeout_seconds`. Keep it off outside the harness. |
| `OTEL_SERVICE_NAME` | `ai-filing-analyst` | The service name in Scout. |
| `OTEL_RESOURCE_ATTRIBUTES` | `service.version=1.0.0` | Added to the resource. |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://otel-collector:4318` | Use `http://localhost:4318` on the host. |
| `OTEL_EXPORTER_OTLP_PROTOCOL` | `http/protobuf` | OTLP over HTTP. |
| `OTEL_SDK_DISABLED` | `false` | `true` runs the API with no telemetry. |
| `OTEL_TRACES_SAMPLER` | `parentbased_always_on` | Keeps every trace. |
| `OTEL_METRIC_EXPORT_INTERVAL` | `10000` | Milliseconds. |
| `OTEL_ATTRIBUTE_VALUE_LENGTH_LIMIT` | `4096` | Caps captured content. |
| `OTEL_BSP_SCHEDULE_DELAY`, `OTEL_BSP_MAX_EXPORT_BATCH_SIZE` | `5000`, `512` | Batch span processor delay in milliseconds, and batch size. |
| `OTEL_SEMCONV_STABILITY_OPT_IN` | `gen_ai_latest_experimental` | Read by Strands. |
| `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT` | `true` | See [Content capture](#content-capture). |
| `OTEL_PYTHON_LOG_CORRELATION` | `true` | Trace and span IDs in the console log lines. Exported records carry them either way. |
| `SCOUT_ENVIRONMENT` | empty | Compose falls back to `development`. |
| `SCOUT_CLIENT_ID`, `SCOUT_CLIENT_SECRET`, `SCOUT_TOKEN_URL`, `SCOUT_ENDPOINT` | empty | Read by the collector only. See [Scout export](#scout-export). |

`compose.yaml` also sets `FILING_DB_DSN` to the Compose Postgres and `FIXTURES_DIR` to `/app/fixtures`. The
Dockerfile's `uvicorn` command binds the API to port 8000.

## Known gaps

Checked on 2026-09-29 against the versions in `uv.lock`. Each list says what the framework emits on its own, and what
this example had to add or cannot fix.

### Strands Agents 1.57.1

- **`gen_ai.provider.name` is `strands-agents`**, not the model provider, and no span carries `server.address` or
  `server.port`. The example overrides both through `trace_attributes`.
- **No `error.type`.** Strands records the exception on a failed span without `error.type`. The exporter here adds
  it.
- **No OTLP logs.** Strands logs through standard `logging` and exports nothing. The `LoggingHandler` here exports
  them.
- **Metric names are Strands' own.** It records `strands.*` metrics, not the semconv `gen_ai.client.*` ones.
- **Cache token metrics are missing on Ollama.** `strands.event_loop.cache_read.input.tokens` and
  `cache_write.input.tokens` are recorded only when the provider reports prompt caching, and Ollama does not.
- **A tool hook that raises loses the tool span.** Strands opens `execute_tool` before `BeforeToolCallEvent` and does
  not end it if a hook raises. The call budget cancels the tool through `cancel_tool` instead, and stops the run at
  the next model call.

### Google ADK 2.10.0

- **OpenTelemetry is capped at 1.42.1.** ADK pins the API and SDK, so this framework's environment runs an older
  OpenTelemetry than the other three.
- **The model name carries the LiteLLM route.** `gen_ai.request.model` reads `ollama_chat/qwen3.5:9B`, and the
  metrics report the provider as `ollama_chat`. ADK's spans have no provider; the exporter sets `ollama` on
  model-call spans only.
- **Failed agent and model spans have no `error.type`.** They have error status and the exception; the metrics carry
  `error.type`. The exporter here takes the type from the exception.
- **The ranking agent has its own conversation ID.** ADK runs the agent tool in a new session, so its spans carry
  that session's UUID rather than the question ID.
- **A failed tool has `error.type` `TOOL_ERROR`** and no `gen_ai.tool.status`.
- **Content capture has its own switch.** ADK records content on its spans unless
  `ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS` is false. The adapter sets it from
  `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT`.
- **`set_model_response` is listed first.** ADK puts its answer tool ahead of the agent's tools, and with its schema
  first the model passes years it assumes to `query_facts`. The model callback moves it to the end of the list.
- **`bad_output` is applied after the run.** `set_model_response` succeeds, and validation fails on the rewritten
  answer.

### Microsoft Agent Framework 1.19.0

- **`chat` spans have `server.address` `Unknown`.** The Ollama client does not report its host.
- **`invoke_agent` reports the provider as `microsoft.agent_framework`.** The exporter sets `ollama` on model-call
  spans only, so the agent spans keep it.
- **`response_format` cannot be used with tools on Ollama.** Ollama applies the schema to every call, so the model
  cannot call a tool. The analyst answers through the `FilingAnswer` tool instead.
- **`agent-framework-ollama` is a beta.** It pins `ollama` below 0.5.4.
- **`bad_output` is applied after the run.** `FilingAnswer` succeeds, and validation fails on the rewritten answer.

### OpenAI Agents SDK 0.22.3

- **The instrumentation sets `error.type` `_OTHER`** on a failed `invoke_agent`, with no exception. The run hooks
  record the exception on the span, and the exporter here takes the type from it.
- **Model-call spans report the provider as `openai`** for Ollama's `/v1` endpoint. The exporter sets `ollama`.
- **Strict tool schemas are off.** A strict schema marks every parameter required, and the model then fills an
  optional year with the text `None`. The tools are registered with `strict_mode=False`.
- **`output_type` cannot be used with tools on Ollama**, for the same reason as MAF's `response_format`.
- **Content capture takes a mode, not `true`.** The adapter maps
  `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT` to `SPAN_ONLY` or `NO_CONTENT`.
- **The SDK's own trace export is off.** The instrumentor replaces it, so no trace goes to OpenAI.
- **`bad_output` is applied after the run.** `FilingAnswer` succeeds, and validation fails on the rewritten answer.

### On every framework

- **Frames repeat filers' tagging errors.** A frame is what each company tagged, so a mis-scaled filing can lead the
  five largest filers.
- **Cost on local models is zero.** Neither model has a row in `_shared/pricing.json`.

## Development

```bash
make dev                      # one framework's extra and the dev tools, in .venv-strands
make check                    # ruff, ruff format --check, mypy, and the unit tests, on Strands
make check FRAMEWORK=adk      # the same on one framework, in .venv-adk
make check-all                # the same on all four
make test-integration         # the Postgres store and advisory lock tests, against Postgres on localhost:5433
make run FRAMEWORK=maf        # the API on the host, port 8000
```

The framework extras conflict, since ADK needs an older OpenTelemetry than the OpenAI Agents instrumentation, so each
framework gets its own virtual environment, `.venv-<framework>`. The unit tests run each adapter on a scripted model
and the SEC client on a mock transport, so they need no Ollama and no network. Tests for a framework that is not
installed are skipped. `make test-integration` needs the stack up.

## Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| The API exits at startup with a settings error naming `SEC_USER_AGENT`. | Set it in `.env` to a name and contact email. |
| Questions answer 502 `model_unavailable`. | Ollama is not reachable from the container, or a model is not pulled. Check `ollama list` and that `OLLAMA_BASE_URL` is `http://host.docker.internal:11434`. |
| `base14.gen_ai.model.digest` reads `unknown`. | Ollama was not reachable when the API started. Restart the API once Ollama is up. |
| Questions on new companies answer 503 `sec_backoff`. | The SEC answered 403 and the back-off is in force. Wait `SEC_BACKOFF_SECONDS`, and check that `SEC_USER_AGENT` names you. |
| `POST /questions` answers 422 `faults_disabled`. | Restart with `FILING_FAULTS_ENABLED=true docker compose up -d --build`. |
| `scripts/test-api.sh` exits with `API not reachable`. | The stack is not up, or the API is still starting. Check `docker compose ps`. |
| `docker compose logs otel-collector` shows `otlp_http/b14` export errors. | Scout credentials are empty or wrong. The `debug` output is unaffected. |
| `scripts/verify-scout.sh` fails the Scout send counts. | The collector restarted after the run, or its self-metrics on port 8888 were not reachable when the run started. Rerun `scripts/test-api.sh`, then verify without restarting anything. |
| Edits to `db/01-schema.sql` have no effect. | Postgres runs it only on an empty volume. `make docker-down` deletes the volume. |

## Project layout

```text
ai-filing-analyst/
|-- compose.yaml                 Postgres, collector, api
|-- otel-collector-config.yaml   debug and Scout exporters
|-- db/01-schema.sql             companies, facts, fact_loads
|-- fixtures/                    ticker list and cached company facts, with MANIFEST.json
|-- prompts/                     analyst and ranking prompts, named by UTC timestamp
|-- scripts/
|   |-- test-api.sh              the seventeen scenarios
|   |-- verify-scout.sh          checks the run's telemetry in the collector output
|   |-- verify_questions.py      the per-question checks behind verify-scout.sh
|   |-- collector_debug.py       parses the collector's debug output
|   `-- fetch-fixtures.sh        refreshes the cache from the SEC
|-- src/filing_analyst/
|   |-- main.py                  FastAPI app and startup
|   |-- api.py                   question handling, refusals, server span attributes
|   |-- agents.py                what the adapters share: prompts, ranking report, answer tool, errors
|   |-- frameworks/
|   |   |-- strands.py           Strands hooks and agents
|   |   |-- strands_faults.py    the model wrapper that injects faults on Strands
|   |   |-- adk.py               ADK callbacks and agents, LiteLLM to Ollama
|   |   |-- maf.py               Agent Framework middleware and agents
|   |   `-- openai_agents.py     OpenAI Agents run hooks and agents, Ollama's /v1 endpoint
|   |-- budget.py                the call budget shared by both agents
|   |-- tools.py                 query_facts, compute_ratio, frame_values
|   |-- verifier.py              the grounding check and the tool result collector
|   |-- sec_client.py            rate limit, retries, back-off, SEC faults
|   |-- loader.py                loads a company's facts from the cache or the SEC
|   |-- model_faults.py          model faults for the scenarios
|   |-- telemetry.py             providers, logging, derived span attributes
|   `-- app_metrics.py           application metrics
`-- tests/
```

## References

- [AI Agent Observability](https://docs.base14.io/guides/ai-observability/agent-observability/), for agent
  timelines and tool calls.
- [LLM Observability](https://docs.base14.io/guides/ai-observability/llm-observability/), for token, cost and
  latency signals.
- [Collector Setup](https://docs.base14.io/category/opentelemetry-collector-setup), for pointing a collector at
  your Scout tenant.
- [Strands Agents traces](https://strandsagents.com/docs/user-guide/sdk/observability-evaluation/traces/).
- [SEC EDGAR APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) and
  [accessing EDGAR data](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data).
- [OpenTelemetry GenAI semantic conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/).
