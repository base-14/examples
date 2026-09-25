# AI KYC Onboarding Agent

A KYC (know your customer) onboarding service where each case is a Temporal workflow and the decisions come from two
Pydantic AI agents running on local Ollama models. An applicant's documents arrive as workflow signals, an extraction
agent reads each one into typed fields, and an assessment agent checks expiry, identity and sanctions with three tools
before it approves, asks for documents again or escalates to a human reviewer. A case can wait days for documents or
a review, survive a worker crash, and still come out as one trace, with trace-correlated logs and application metrics
exported to base14 Scout.

**Stack**: Python 3.14 · FastAPI 0.141 · Pydantic AI 2.49 · Temporal (Python SDK 1.33, server 1.32) · PostgreSQL 18 ·
Ollama (local models) · OpenTelemetry SDK 1.44 · base14 Scout

One of the [Python examples](../README.md) in base14's [OpenTelemetry examples](../../README.md) repository. For an
agent without durable execution, read [ai-runbook-assistant](../ai-runbook-assistant) (LangChain and LangGraph). Other
links are under [References](#references).

## How to instrument a Pydantic AI agent on Temporal with OpenTelemetry

All of it lives in `src/kyc_onboarding/telemetry.py`. The API (`main.py`) and the worker (`worker.py`) both call
`configure_telemetry` at startup and connect to Temporal through `create_temporal_client`.

1. Install `pydantic-ai-slim[temporal,openai]`, `temporalio[opentelemetry]`, `opentelemetry-sdk`, the OTLP HTTP
   exporter and the FastAPI, psycopg and logging instrumentations, as pinned in `pyproject.toml`.
2. Build the tracer provider with `create_tracer_provider` from `temporalio.contrib.opentelemetry`, not a plain
   `TracerProvider`. Spans started in workflow code are then emitted once, not again on every replay. Add a
   `BatchSpanProcessor` around the OTLP exporter and set it as the global provider.
3. Wrap the meter provider in `ReplaySafeMeterProvider` and the logger provider in `ReplaySafeLoggerProvider`, so
   metrics recorded and lines logged from workflow code are dropped during replay. Route standard `logging` into the
   logger provider with `LoggingHandler`.
4. Call `Agent.instrument_all(InstrumentationSettings(include_content=...))` so every Pydantic AI agent emits GenAI
   spans (`invoke_agent`, `chat`, `execute_tool`) and the `gen_ai.client.token.usage` metric.
5. Connect the client with `plugins=[PydanticAIPlugin(), OpenTelemetryPlugin(add_temporal_spans=True)]`.
   `OpenTelemetryPlugin` propagates trace context through Temporal and adds the `StartWorkflow`, `RunWorkflow`,
   `StartActivity`, `RunActivity`, signal, update and query spans. `PydanticAIPlugin` registers the agent activities.
   The client's `Runtime` exports Temporal SDK metrics to the same collector.
6. On the worker, add `AgentPlugin` for each agent and `ActivityAttemptInterceptor` (`interceptors.py`) in
   `Worker(interceptors=...)`. The interceptor writes the attempt number on each `RunActivity` span.
7. Set `OTEL_SERVICE_NAME`, `OTEL_EXPORTER_OTLP_ENDPOINT` and `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT` as
   `.env.example` and `compose.yaml` ship them. The OTLP exporters read the endpoint and add each signal's path. The
   Temporal runtime does not read it, so `telemetry.py` passes it `<endpoint>/v1/metrics`.

## Prerequisites

- Python 3.14 and [uv](https://docs.astral.sh/uv/), for the checks, the tests and `scripts/verify-scout.sh`.
- Docker and Docker Compose.
- `curl` and `jq`, for the quick start and the scenario harness.
- Ollama on the host, with both models pulled: `ollama pull gemma4:e2b` and `ollama pull qwen3.5:9B`. They are about
  7.2 GB and 6.6 GB on disk. A case calls them back to back, so the machine needs room for both next to Docker.
- base14 Scout credentials, optional. Without them the collector still starts and prints everything through its
  `debug` exporter, but every send to Scout fails and the collector logs the errors. See [Scout export](#scout-export).

No LLM provider key is needed. Every model call goes to Ollama.

## Quick start

```bash
cp .env.example .env
ollama pull gemma4:e2b
ollama pull qwen3.5:9B
make docker-up
```

`.env` needs no edits to run locally. Fill in the four `SCOUT_*` variables to export to Scout.

This starts Postgres, the Temporal server, the Temporal UI at <http://localhost:8080>, the collector, the `api`
service on port 8000 and the `worker` service. Postgres is on host port 5433. Its `kyc` database holds the sanctions
list and the `case_faults` table.

Start a case. The response carries the `case_id`, which is also the Temporal workflow ID.

```bash
CASE_ID=$(curl -s -X POST http://localhost:8000/cases \
  -H 'Content-Type: application/json' \
  -d '{"name": "Maria Elena Gonzalez", "country": "IE", "account_type": "personal"}' | jq -r .case_id)
```

Submit the documents from a fixture set. A personal account needs `id` and `proof_of_address`. A business account also
needs `registration_certificate`.

```bash
for file in fixtures/clean_personal/*.txt; do
  jq -nc --arg document_type "$(basename "$file" .txt)" --rawfile raw_text "$file" \
    '{document_type: $document_type, raw_text: $raw_text}' \
  | curl -s -X POST "http://localhost:8000/cases/$CASE_ID/documents" \
      -H 'Content-Type: application/json' -d @-
done
```

Read the status. A clean case usually settles in under a minute once both models are loaded. A cold model can take
over a minute on its first request.

```bash
curl -s "http://localhost:8000/cases/$CASE_ID" | jq
```

```json
{
  "case_id": "56f0e40c-1050-4ff5-b740-7e03da327202",
  "account_type": "personal",
  "status": "approved",
  "missing_documents": [],
  "resubmission_round": 0,
  "decisions": [{"decision": "approve"}],
  "review": null,
  "outcome": "approved",
  "escalation_reason": null
}
```

To see a review, start a case for `Alexander Petrov Volkov` with `country` `GB` and send `fixtures/partial_sanctions_match`.
The name is a near match on the sanctions list, so the case stops at `awaiting_review`. Submit the reviewer's decision:

```bash
curl -s -X POST "http://localhost:8000/cases/$CASE_ID/review" \
  -H 'Content-Type: application/json' \
  -d '{"decision": "approve", "reviewer": "r.okafor"}'
```

`decision` is `approve` or `reject`, and an optional `note` is kept with it. The response is the closed case.

`make docker-down` stops the stack and deletes the Postgres volume, which holds every case and all Temporal history.

## Agent workflow

Each case is one Temporal workflow. Documents arrive as signals, the two Pydantic AI agents run inside the workflow,
and a reviewer's decision arrives as an update.

```mermaid
flowchart TD
    start([POST /cases]) --> docs
    docs["awaiting_documents<br/>documents arrive as signals"]
    docs -->|all documents in| extract
    docs -->|deadline| expired([expired])
    extract["extraction agent<br/>gemma4:e2b, one run per document"] --> assess
    assess{"assessment agent<br/>qwen3.5:9B"}
    assess -->|tool call| tools
    subgraph tools [Tools]
        check_expiry
        compare_identity
        screen_sanctions
    end
    tools -->|tool result| assess
    assess -->|approve| approved([approved])
    assess -->|request_resubmission| docs
    assess -->|escalate, budget or error| review
    review["awaiting_review<br/>decision arrives as an update"]
    review -->|approve or reject| closed([approved or rejected])
    review -->|deadline| expired
```

- The extraction agent returns the typed fields for each document.
- The assessment agent must call all three tools before it answers with `approve`, `request_resubmission` or
  `escalate`. A run that hits its budget or fails escalates too.
- `request_resubmission` starts a new document round. A third request rejects the case.
- Every model request and tool call runs as a Temporal activity, so a case survives a worker restart.

## How a case runs

1. **Documents.** The case waits in `awaiting_documents` until every required document has arrived. Each document is a
   signal. A document of a type already submitted replaces the earlier one. The document deadline is 3 days per round.
   If it passes, the case closes as `expired`.
2. **Extraction.** In `assessing`, the extraction agent (`kyc-extraction`, `gemma4:e2b`) reads each new document and
   returns the typed fields for its type. Fields of the wrong type escalate the case as `invalid_output`.
3. **Assessment.** The assessment agent (`kyc-assessment`, `qwen3.5:9B`) must call three tools before it answers:
   `check_expiry`, `compare_identity` (names, dates of birth and addresses across the documents) and
   `screen_sanctions` (an exact match, or a `pg_trgm` similarity of 0.4 or more for a near match). `check_expiry`
   reports a `status` of `valid`, `expired` or `missing`; a missing date is not treated as expired. It answers with
   `approve`, `request_resubmission` with the documents to resend, or `escalate` with a risk level. An answer given
   before all three tools have returned is sent back to the model, and so is an `approve` after `check_expiry` reported
   the expiry date missing. The `v3` prompt tells the model to request the ID again in that case.
4. **Resubmission.** `request_resubmission` drops the named documents and sends the case back to step 1 in the next
   round. After two rounds, a third request rejects the case.
5. **Review.** An escalated case waits in `awaiting_review` for `POST /cases/{id}/review`. The review deadline is 2
   days. If it passes, the case closes as `expired`.
6. **Budget.** Model requests are capped at 40 for the whole case, 3 per extraction run and 10 per assessment run.

A case escalates to review for one of four reasons, reported as `escalation_reason`:

| Reason | When |
| --- | --- |
| `risk` | The assessment agent chose `escalate`. |
| `budget` | A run hit its request limit (`UsageLimitExceeded`). |
| `invalid_output` | The model's output still failed validation after its retries, extraction returned the wrong document type, or a resubmission named no documents. |
| `agent_error` | An agent activity failed after all its retries, or the run failed some other way. |

Every model request and tool call is a Temporal activity. Model requests have a 120 second timeout and tool calls 30
seconds, each with up to five attempts and exponential backoff (`agents/extraction.py`).

## Endpoints

| Method and path | Temporal operation | Responses |
| --- | --- | --- |
| `GET /health` | None | 200. Its spans are dropped by the collector. |
| `POST /cases` | Start workflow | 201 with the case. 422 on a malformed body, or on `fault`, `document_deadline_seconds`, `review_deadline_seconds` or `request_budget` while `KYC_FAULTS_ENABLED` is not `true`. |
| `POST /cases/{case_id}/documents` | Signal `submit_document` | 202. 404 unknown case, 409 closed case, 422 malformed body. |
| `POST /cases/{case_id}/review` | Update `submit_review` | 200 with the closed case. 404 unknown or closed case, 409 case not awaiting a review. |
| `GET /cases/{case_id}` | Query `status` | 200. 404 unknown case. |

`status` is one of `awaiting_documents`, `assessing`, `awaiting_review`, `approved`, `rejected` and `expired`.

## Scenarios

`scripts/test-api.sh` drives eleven scenarios against the running stack and checks each outcome. Five of them inject a
failure, so start the stack with faults enabled:

```bash
KYC_FAULTS_ENABLED=true docker compose up -d --build
scripts/test-api.sh                      # all eleven
scripts/test-api.sh expired bad_output   # a subset
```

A full run takes around ten minutes. Results, case IDs and a per-case activity summary go to `.harness/last-run.json`.

| Scenario | Fixtures | Fault | Outcome | What to look for in the trace |
| --- | --- | --- | --- | --- |
| `auto_approved` | `clean_personal` | None | `approved` | Two `invoke_agent kyc-extraction`, one `invoke_agent kyc-assessment` with three `execute_tool` spans. |
| `approved_after_resubmission` | `address_mismatch`, then `corrected_address` | None | `approved`, round 1 | Two `kyc.await_documents` and two `kyc.assess` spans. The first `kyc.assess` carries `base14.kyc.documents_to_resend`. |
| `approved_by_reviewer` | `partial_sanctions_match` | None | `approved` after review | `base14.kyc.sanctions.result=near_match` on the tool activity, `kyc.await_review`, and `kyc.review_received` linked to the update's trace. |
| `rejected_by_reviewer` | `partial_sanctions_match` | None | `rejected` after review | The same, with `base14.kyc.review_decision=reject`. |
| `rejected_automatically` | `expired_id`, resent twice | None | `rejected`, round 2 | Three `kyc.assess` spans, each deciding `request_resubmission`. |
| `expired` | None | 5 second document deadline | `expired` | One `kyc.await_documents` with `base14.kyc.missing_documents` and a WARN `document deadline passed` line. |
| `worker_crash` | `clean_business` | Worker killed with SIGKILL during an assessment model request | `approved` | Spans and logs from two worker `service.instance.id` values in one trace. The killed activity shows only its rerun, one attempt higher. |
| `model_unavailable` | `clean_personal` | The first model request fails twice | `approved` | Two `RunActivity:agent__kyc-extraction__model_request` spans with error status and an ERROR `injected model_unavailable fault` line each, then attempt 3 succeeds. |
| `sanctions_down` | `clean_personal` | Every `screen_sanctions` call fails three times | `approved` | Three failed tool attempts per screening with `base14.kyc.sanctions.result=error`, then attempt 4 succeeds. |
| `tight_budget` | `clean_personal` | Assessment limited to one request | `approved` after review | `invoke_agent kyc-assessment` with error status and `error.type=pydantic_ai.exceptions.UsageLimitExceeded`, and `base14.kyc.escalation_reason=budget` on `kyc.assess`. |
| `bad_output` | `clean_personal` | One extraction response turned into plain text | `approved` | One extra `chat` span under an extraction run, carrying the retry. |

A fault is chosen per case in the `fault` field of `POST /cases` and stored in `case_faults`. Each fires once per
case. `worker_crash` waits for the extraction spans to be exported before the kill, and Temporal retries the killed
attempt after its 30 second heartbeat timeout.

Then check the telemetry the run produced:

```bash
scripts/verify-scout.sh
scripts/verify-scout.sh --allow-partial   # after running a subset
```

It reads the collector's `debug` output and self-metrics for the run and checks, per case: one trace rooted at
`POST /cases > StartWorkflow > RunWorkflow`, the expected span names and wait spans, the links from arrival spans to
the signal and update handler spans, the case log lines on the right spans, the `base14.*` and `gen_ai.*` attributes,
and each scenario's failure shape. It also checks that every application metric data point the run should produce is
there, and that the Scout exporter sent spans, log records and metric points with no failures. Do not restart the
collector between the run and the verification, since its self-metrics reset on restart.

## Telemetry

The API and the worker export traces, metrics and logs over OTLP HTTP to the collector, as the services
`ai-kyc-onboarding-api` and `ai-kyc-onboarding-worker`. Each process gets a fresh `service.instance.id`.

### The trace of one case

A case is one trace, from `POST /cases` to the close, however long it waits. This one was escalated for a near
sanctions match and approved by a reviewer. `SELECT` spans from psycopg and a few chat turns are elided.

```text
POST /cases                                           api, base14.kyc.case_id, base14.kyc.account_type
`-- StartWorkflow:KycOnboardingWorkflow               api
    `-- RunWorkflow:KycOnboardingWorkflow             worker, ends when the case closes
        |-- kyc.await_documents                       round 0
        |   |-- kyc.document_received                 id, linked to its HandleSignal span
        |   `-- kyc.document_received                 proof_of_address
        |-- kyc.assess
        |   |-- invoke_agent kyc-extraction           one per document
        |   |   `-- chat gemma4:e2b
        |   |       `-- StartActivity:agent__kyc-extraction__model_request
        |   |           `-- RunActivity:agent__kyc-extraction__model_request
        |   |-- invoke_agent kyc-extraction
        |   |   `-- chat gemma4:e2b ...
        |   `-- invoke_agent kyc-assessment
        |       |-- chat qwen3.5:9B ...
        |       |-- execute_tool compare_identity
        |       |   `-- StartActivity:agent__kyc-assessment__toolset__<agent>__call_tool
        |       |       `-- RunActivity:agent__kyc-assessment__toolset__<agent>__call_tool
        |       |-- execute_tool screen_sanctions ...
        |       |-- execute_tool check_expiry ...
        |       |-- chat qwen3.5:9B ...
        |       `-- execute_tool decision_from_answer    the answer, checked by the output function
        `-- kyc.await_review
            `-- kyc.review_received                   linked to its HandleUpdate span
```

Documents, reviews and status reads are separate requests, so each has its own trace:
`POST /cases/{case_id}/documents > SignalWorkflow:submit_document > HandleSignal:submit_document`,
`POST /cases/{case_id}/review > StartWorkflowUpdate:submit_review > ValidateUpdate` and `HandleUpdate:submit_review`,
and `GET /cases/{case_id} > QueryWorkflow:status > HandleQuery:status`. The `kyc.document_received` and
`kyc.review_received` spans in the case trace carry a span link to the handler span in the request's trace, which is
how you get from the case to the request that moved it and back.

### Hand-written spans

`workflows.py` adds five spans, all under `RunWorkflow`:

| Span | Covers |
| --- | --- |
| `kyc.await_documents` | One document round, from the start of the wait until the documents are complete or the deadline passes. |
| `kyc.document_received` | The workflow taking in one signalled document. |
| `kyc.assess` | Extraction of new documents and one assessment run. |
| `kyc.await_review` | The wait for a reviewer, until a decision or the deadline. |
| `kyc.review_received` | The workflow taking in the reviewer's decision. |

### Attributes this example adds

All under `base14.`, since semconv owns `gen_ai.*`. The keys are defined in `src/kyc_onboarding/attributes.py`.

| Span | Attributes |
| --- | --- |
| `POST /cases` | `base14.kyc.case_id`, `base14.kyc.account_type`. |
| `POST /cases/{case_id}/documents` | `base14.kyc.case_id`, `base14.kyc.document_type`. |
| `POST /cases/{case_id}/review` | `base14.kyc.case_id`, `base14.kyc.review_decision`. |
| `GET /cases/{case_id}` | `base14.kyc.case_id`. |
| `RunWorkflow:KycOnboardingWorkflow` | `base14.kyc.case_id` and `base14.kyc.account_type` from the start. `base14.kyc.resubmission_round`, `base14.kyc.outcome` and, if escalated, `base14.kyc.escalation_reason` at the close. |
| `kyc.await_documents` | `base14.kyc.case_id`, `base14.kyc.account_type`, `base14.kyc.resubmission_round`. `base14.kyc.missing_documents` when the deadline passes. |
| `kyc.document_received` | `base14.kyc.case_id`, `base14.kyc.document_type`. |
| `kyc.assess` | `base14.kyc.case_id`, `base14.kyc.account_type`, `base14.kyc.resubmission_round`, `base14.prompt.version`, `base14.kyc.assessment_decision`. `base14.kyc.risk_level` on `escalate`, `base14.kyc.documents_to_resend` on `request_resubmission`, `base14.kyc.escalation_reason` when escalated. |
| `kyc.await_review` | `base14.kyc.case_id`, `base14.kyc.account_type`, `base14.kyc.resubmission_round`, `base14.kyc.escalation_reason`. |
| `kyc.review_received` | `base14.kyc.case_id`, `base14.kyc.review_decision`. |
| Every `RunActivity:*` | `base14.temporal.activity.attempt`, from the interceptor. |
| `RunActivity` of a `screen_sanctions` call | `base14.kyc.sanctions.result` (`clear`, `near_match`, `match` or `error`) and `base14.kyc.sanctions.score` when the lookup returned one. Never the matched name. |
| `chat *` | `base14.gen_ai.cost`, `base14.gen_ai.cost.simulated`. `error.type` when the span has error status. |
| `invoke_agent *` | `base14.prompt.version`. `error.type` when the span has error status. |

The `chat` and `invoke_agent` spans belong to Pydantic AI and are finished before this code sees them, so
`CostAndErrorAttributingSpanExporter` in `telemetry.py` adds their attributes on the way to the OTLP exporter. It
computes the cost, copies the prompt version out of the run's `metadata`, and takes `error.type` from the span's first
recorded exception.

### GenAI spans

Pydantic AI emits `invoke_agent <agent>` per run, `chat <model>` per model request and `execute_tool <tool>` per tool
call, following the GenAI semantic conventions. The keys worth knowing:

- `gen_ai.conversation.id` is the case ID on every GenAI span, so one filter finds every model call of a case.
- `gen_ai.agent.name` is `kyc-extraction` or `kyc-assessment`, and `gen_ai.agent.description` says what the agent does.
- `gen_ai.provider.name` is `ollama`, with `server.address` and `server.port` pointing at it.
- `gen_ai.request.model`, `gen_ai.response.model`, `gen_ai.request.temperature` (0) and `gen_ai.request.max_tokens`
  (1024).
- `gen_ai.usage.input_tokens` and `gen_ai.usage.output_tokens` on `chat`, and `gen_ai.aggregated_usage.*` on
  `invoke_agent`.
- `gen_ai.response.finish_reasons` on `chat`.
- `gen_ai.tool.name`, `gen_ai.tool.call.arguments` and `gen_ai.tool.call.result` on `execute_tool`.

### Cost

`base14.gen_ai.cost` is computed from the token counts and the model's row in `_shared/pricing.json`. The local models
have no row, so their cost is 0 and `base14.gen_ai.cost.simulated` is `true`. A model with a row gets a real cost and
`false`.

### Logs

Standard `logging` goes to the collector through the replay-safe logger provider. Every line logged inside a request,
workflow or activity carries the trace ID and span ID of the span it was logged on, and every case line carries
`base14.kyc.case_id`.

| Line | Level | Span |
| --- | --- | --- |
| `case created` | INFO | `POST /cases` |
| `document accepted`, `review accepted` | INFO | The request's server span. |
| `request refused: ...` | WARN | The request's server span, with `http.response.status_code`. |
| `documents complete` | INFO | `kyc.await_documents` |
| `document deadline passed` | WARN | `kyc.await_documents`, with `base14.kyc.missing_documents`. |
| `assessment decided <decision>` | INFO | `kyc.assess` |
| `case escalated for review` | WARN | `kyc.assess`, with `base14.kyc.escalation_reason`. |
| `agent run failed` | ERROR | `kyc.assess`, with the exception. |
| `resubmission requested` | INFO | `RunWorkflow`, with the round and the documents to resend. |
| `review deadline passed` | WARN | `kyc.await_review` |
| `case closed` | INFO | `RunWorkflow`, with the outcome. |
| `sanctions near match` | WARN | The tool's `RunActivity`, with the score. |
| `sanctions lookup failed` | ERROR | The tool's `RunActivity`. |
| `injected <fault> fault` | ERROR | The failing `RunActivity`, with the attempt. |

To go from a log line to its trace, open the trace ID on the line. It lands on the span that logged it, inside the
case trace or the request trace. To go from a trace to its logs, filter logs by the trace ID for that trace alone, or
by `base14.kyc.case_id` for every line of the case across its request traces. Workflow and activity lines also carry
Temporal's `temporal_workflow` or `temporal_activity` attribute with the workflow ID, run ID and attempt.

### Application metrics

Defined in `src/kyc_onboarding/case_metrics.py`. Workflow code records through the replay-safe meter provider, so
replay records nothing. Durations are in workflow time, and the histograms share buckets from 1 second to 7 days.

| Instrument | Type | Attributes |
| --- | --- | --- |
| `base14.kyc.cases` | counter, `{case}` | `base14.kyc.outcome`, `base14.kyc.escalation_reason` when escalated. |
| `base14.kyc.case.duration` | histogram, seconds | `base14.kyc.outcome` |
| `base14.kyc.resubmissions` | counter, `{document}` | `base14.kyc.document_type` |
| `base14.kyc.review.wait` | histogram, seconds | `base14.kyc.review_decision` (`approve`, `reject` or `expired`) |
| `base14.kyc.sanctions.checks` | counter, `{check}` | `base14.kyc.sanctions.result` (`clear`, `near_match`, `match` or `error`) |

Pydantic AI adds `gen_ai.client.token.usage`, by `gen_ai.token.type`, model and provider. The FastAPI instrumentation
adds the `http.server.*` metrics.

### Temporal SDK metrics

The Temporal client's runtime exports the SDK's own metrics over OTLP HTTP to the same collector. Among them are
`temporal_workflow_completed`, `temporal_workflow_endtoend_latency`, `temporal_activity_execution_failed`,
`temporal_activity_execution_latency`, `temporal_activity_schedule_to_start_latency`,
`temporal_workflow_task_replay_latency`, `temporal_sticky_cache_hit` and `temporal_worker_task_slots_used`.

### Content capture

`OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT` is `true` in `.env.example` and `compose.yaml`, because the
fixtures are synthetic. Pydantic AI then records system instructions, prompts, completions, tool arguments and tool
results on its spans. Set it to `false` for real applicant data. Token counts and the other attributes are recorded
either way.

Temporal history is a second copy of the same data. The document text travels in the signal payloads and the activity
inputs, and Temporal stores it whatever the capture setting is.

## Scout export

The collector (`otel-collector-config.yaml`) exports every pipeline to Scout through the `otlp_http/b14` exporter,
authenticated by the `oauth2client` extension, and to the `debug` exporter. Fill in `SCOUT_CLIENT_ID`,
`SCOUT_CLIENT_SECRET`, `SCOUT_TOKEN_URL` and `SCOUT_ENDPOINT` in `.env`, then start or recreate the stack.
`SCOUT_ENVIRONMENT` is written as `deployment.environment.name` and `environment` on every span, log record and data
point, and defaults to `development`.

With the credentials empty, `compose.yaml` passes `unset` as the client ID and secret, so the collector starts and the
`debug` output is complete, but every send to Scout fails. `scripts/test-api.sh` still passes. `scripts/verify-scout.sh`
reports the Scout exporter checks as failed.

`scripts/verify-scout.sh` is the check that the export worked. It takes the collector's exporter counters at the end
of the run, subtracts the values `scripts/test-api.sh` recorded at its start, and passes when spans, log records and
metric points were sent to `otlp_http/b14` with none failed and no exporter warnings or errors in the collector log.

## Configuration

`.env.example` ships these values. Compose reads `.env` when it starts the stack. The app itself reads only its
environment, so host runs take the defaults in `src/kyc_onboarding/config.py` unless you export the variables.

| Variable | `.env.example` | Notes |
| --- | --- | --- |
| `TEMPORAL_TASK_QUEUE` | `kyc-onboarding` | The API starts workflows on it and the worker polls it. |
| `OLLAMA_BASE_URL` | `http://host.docker.internal:11434` | Without `/v1`, which the code adds. Use `http://localhost:11434` on the host. |
| `EXTRACTION_MODEL` | `gemma4:e2b` | Worker only. |
| `ASSESSMENT_MODEL` | `qwen3.5:9B` | Worker only. |
| `EXTRACTION_PROMPT_VERSION` | `v1` | Loads `prompts/extraction_v1.yaml`. The API stamps it on each case and the worker loads it. |
| `ASSESSMENT_PROMPT_VERSION` | `v3` | Loads `prompts/assessment_v3.yaml`. `v2` lacks the missing-expiry instruction. The API stamps it on each case and the worker loads it. |
| `KYC_DB_DSN` | `postgresql://temporal:temporal@postgres:5432/kyc` | The sanctions list and `case_faults`. Use host port 5433 on the host. |
| `KYC_FAULTS_ENABLED` | `false` | `true` lets `POST /cases` take a fault and the deadline and budget overrides, and makes the worker read `case_faults`. |
| `DOCUMENT_DEADLINE_DAYS` | `3` | Days a case waits for documents. |
| `REVIEW_DEADLINE_DAYS` | `2` | Days a case waits for a reviewer. |
| `REQUEST_BUDGET` | `40` | Model requests a case may make before it escalates with `budget`. |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://otel-collector:4318` | Use `http://localhost:4318` on the host, which is also the default when unset. |
| `OTEL_SDK_DISABLED` | `false` | |
| `OTEL_SEMCONV_STABILITY_OPT_IN` | `gen_ai_latest_experimental` | Compose sets this value directly, not from `.env`. Pydantic AI does not read it; it matches the other AI examples. |
| `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT` | `true` | See [Content capture](#content-capture). |
| `SCOUT_ENVIRONMENT` | empty | Compose falls back to `development`. |
| `SCOUT_CLIENT_ID`, `SCOUT_CLIENT_SECRET`, `SCOUT_TOKEN_URL`, `SCOUT_ENDPOINT` | empty | Read by the collector only. See [Scout export](#scout-export). |

A few more are read but not in `.env.example`. `compose.yaml` sets `OTEL_METRIC_EXPORT_INTERVAL` (10000 ms) on both
services and `OTEL_SERVICE_NAME` as `ai-kyc-onboarding-api` and `ai-kyc-onboarding-worker`. Without `OTEL_SERVICE_NAME`,
a host run reports under those same names. `config.py` also reads `TEMPORAL_ADDRESS`, which Compose sets to
`temporal:7233` and which defaults to `localhost:7233`. The Dockerfile's `uvicorn` command binds the API to port 8000.

## Known gaps

- **An open case has no root in the trace store.** `RunWorkflow` ends when the case closes, so a case that is still
  waiting shows `POST /cases`, `StartWorkflow` and its finished child spans without the `RunWorkflow` span they hang
  from, until it closes.
- **A `kill -9` loses spans.** Spans still in the batch processor's buffer, up to 5 seconds on the worker, go with
  the process. Temporal reruns the activity, so the case is fine, but the killed attempt's spans are missing.
- **Changing the workflow breaks replay for cases in flight.** That includes how the agents' tools and their
  arguments are set up, because every model request and tool call is recorded in the case's history. See
  [Development](#development).
- **Tool results include sanctions list names.** With content capture on, `gen_ai.tool.call.result` on
  `execute_tool screen_sanctions` carries the nearest list entry's name, even for a `clear` result.
- **Cost on local models is zero.** Neither model has a row in `_shared/pricing.json`, so every `chat` span reads
  `base14.gen_ai.cost=0` with `base14.gen_ai.cost.simulated=true`.

## Development

```bash
make dev                # uv sync --all-extras, for pytest, ruff and mypy
make check              # ruff, ruff format --check, mypy, and the unit tests
make test-integration   # the sanctions and fault registry tests, against Postgres on localhost:5433
make run                # the API on the host, port 8000
make run-worker         # the worker on the host
```

The unit tests run workflows in Temporal's time-skipping test environment with scripted agents, so they need no model
and no stack. `make test-integration` needs the stack up.

`tests/test_workflow_replay.py` replays a recorded case history, `tests/histories/resubmission_escalation_review.json`,
against the current workflow and fails on nondeterminism. After an intended change to the workflow's commands,
re-record it and commit the rewritten file:

```bash
uv run python -m tests._record_history
```

## Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| Cases escalate with `agent_error` and no model reply. | Ollama is not reachable from the containers, or a model is not pulled, and the model activity ran out of retries. Check `ollama list` and that `OLLAMA_BASE_URL` is `http://host.docker.internal:11434`. |
| A case stays in `assessing` and the worker logs `case needs prompt versions ..., this worker loaded ...`. | The API and the worker run with different prompt versions, for example during a rolling change. Start both with the same `EXTRACTION_PROMPT_VERSION` and `ASSESSMENT_PROMPT_VERSION`. |
| `POST /cases` answers 422 with `fault and deadline/budget overrides require KYC_FAULTS_ENABLED=true`. | Restart with `KYC_FAULTS_ENABLED=true docker compose up -d --build`. |
| `scripts/test-api.sh` exits with `API not reachable`. | The stack is not up, or the API is still starting. Check `docker compose ps`. |
| `docker compose logs otel-collector` shows `otlp_http/b14` export errors. | Scout credentials are empty or wrong. The `debug` output is unaffected. |
| `scripts/verify-scout.sh` fails the Scout send counts. | The collector restarted after the run, or its self-metrics on port 8888 were not reachable when the run started. Rerun `scripts/test-api.sh`, then verify without restarting anything. |
| Edits to `db/*.sql` have no effect. | Postgres runs them only on an empty volume. `make docker-down` deletes the volume. |

## Project layout

```text
ai-kyc-onboarding/
|-- compose.yaml                 Postgres, Temporal, Temporal UI, collector, api, worker
|-- otel-collector-config.yaml   debug and Scout exporters
|-- db/                          kyc database, sanctions list, case_faults
|-- fixtures/                    document sets for the scenarios
|-- prompts/                     versioned extraction and assessment prompts
|-- scripts/
|   |-- test-api.sh              the eleven scenarios
|   |-- verify-scout.sh          checks the run's telemetry in the collector output
|   |-- verify_cases.py          the per-case checks behind verify-scout.sh
|   |-- collector_debug.py       parses the collector's debug output
|   `-- case_activities.py       reads a case's activities from Temporal
|-- src/kyc_onboarding/
|   |-- main.py                  FastAPI endpoints
|   |-- worker.py                Temporal worker
|   |-- workflows.py             KycOnboardingWorkflow and its spans, logs and metrics
|   |-- telemetry.py             providers, plugins, instrumentation, derived span attributes
|   |-- interceptors.py          activity attempt attribute
|   |-- attributes.py            base14.* attribute keys
|   |-- case_metrics.py          application metrics
|   |-- agents/                  the two agents, their tools, prompts and fault injection
|   |-- tools/                   expiry, identity and sanctions checks
|   `-- models/                  case, document and decision models
`-- tests/
```

## References

- [AI Agent Observability](https://docs.base14.io/guides/ai-observability/agent-observability/), for agent
  timelines and tool calls.
- [LLM Observability](https://docs.base14.io/guides/ai-observability/llm-observability/), for token, cost and
  latency signals.
- [Collector Setup](https://docs.base14.io/category/opentelemetry-collector-setup), for pointing a collector at
  your Scout tenant.
- [Pydantic AI durable execution with Temporal](https://ai.pydantic.dev/durable_execution/temporal/).
- [Temporal Python SDK observability](https://docs.temporal.io/develop/python/observability).
- [OpenTelemetry GenAI semantic conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/).
