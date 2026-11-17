# observed-telemetry.md - claude-code

live-captured 2026-10-04T13:03Z on local Ollama and 2026-10-04T13:07Z on Anthropic's API

## Run context

- **Monitored software**: Claude Code CLI 2.1.289 on macOS (arm64), run headless with `claude -p --bare`, and the
  Claude Agent SDK for Python 0.2.163, which starts its bundled CLI 2.1.286. Telemetry is set by environment
  variables only (`config/telemetry.env`): all three signals over OTLP/HTTP (protobuf) to `localhost:4318`,
  traces enabled with `CLAUDE_CODE_ENHANCED_TELEMETRY_BETA=1`, `OTEL_LOG_TOOL_DETAILS=1`,
  `OTEL_METRICS_INCLUDE_VERSION=true`, `OTEL_METRICS_INCLUDE_ENTRYPOINT=true`, and
  `OTEL_RESOURCE_ATTRIBUTES=team.id=platform`. Prompt and response text are left redacted.
- **Model**: two runs of the same driver. Local Ollama 0.34.2 through its Anthropic-compatible endpoint
  (`ANTHROPIC_BASE_URL=http://localhost:11434`) on `qwen3.5-32k`, which is `qwen3.5:9B` with `num_ctx` 32768
  and `CLAUDE_CODE_MAX_OUTPUT_TOKENS=1024`. Anthropic's API on `claude-haiku-4-5-20251001`, authenticated with
  `ANTHROPIC_API_KEY`.
- **Collector**: `otel/opentelemetry-collector-contrib:0.161.0`, OTLP receiver, debug exporter (verbosity detailed)
  and `otlp_http/b14` to Scout with `oauth2client`.
- **Traffic driver**: `scripts/drive.sh`, six headless turns in a scratch workspace: two turns in one session
  (`--session-id`, then `--resume`), one that runs `ls` through an allow rule, one that edits a file under
  `--permission-mode acceptEdits`, one whose `touch` is denied under `--permission-prompts none`, and one that
  reads a missing file. Then `scripts/sdk-trace.py`: one Agent SDK query under a host span, with the span's
  context passed to the CLI in `TRACEPARENT`.

## Traces

On the Ollama run, one trace per prompt, rooted at `claude_code.interaction`. Every span is INTERNAL, and the
instrumentation scope is `com.anthropic.claude_code.tracing`. The Anthropic run did not keep this shape; see
below.

```text
claude_code.interaction                 one per prompt
├─ claude_code.llm_request              one per model request
└─ claude_code.tool                     one per tool call
   ├─ claude_code.tool.blocked_on_user  permission decision
   └─ claude_code.tool.execution        the tool body; absent when the call is denied
```

- Every span carries `span.type`, `session.id`, `user.id` and `terminal.type`, plus `app.version` and
  `app.entrypoint` (`sdk-cli` for `claude -p`, `sdk-py` for the Python Agent SDK) because the rig turns them on.
  Keys from `OTEL_RESOURCE_ATTRIBUTES` appear both on the resource and as span attributes.
- `claude_code.interaction` carries `user_prompt` (`<REDACTED>`), `user_prompt_length`, `interaction.sequence`,
  `interaction.duration_ms` and `parent.source` (`none`, or `env` when `TRACEPARENT` was read).
- `claude_code.llm_request` carries `model`, `gen_ai.system`, `gen_ai.request.model`, `input_tokens`,
  `output_tokens`, `cache_read_tokens`, `cache_creation_tokens`, `duration_ms`, `ttft_ms`, `first_content_ms`,
  `attempt`, `success`, `stop_reason`, `gen_ai.response.finish_reasons`, `speed`, `llm_request.context` and
  `query_source_safe`, and a `gen_ai.request.attempt` span event per attempt. On Anthropic's API it also carries
  `request_id`, `gen_ai.response.id` and `client_request_id`. `effort` (`high`) is on every request of the Ollama
  run and on none of the Haiku run.
- `claude_code.tool` carries `tool_name`, `tool_name_safe`, `tool_use_id`, `gen_ai.tool.call.id` and
  `duration_ms`. With `OTEL_LOG_TOOL_DETAILS=1` it adds `full_command`, `bash_command_class` and `bash_argv0` for
  Bash, and `file_path` for Read and Edit.
- `claude_code.tool.blocked_on_user` carries `decision` (`accept`, `reject`) and `source` (`config`). On the
  Agent SDK session both read `unknown`, while the `tool_decision` event for the same call reads `accept` and
  `config`.
- `claude_code.tool.execution` carries `success`, and on failure `error` and `error_class`. A failed tool call
  sets span status `Error` on this span only; its parent `claude_code.tool` and every other span stay `Unset`.

Agent SDK query on Ollama: `claude_code.interaction` has `parent.source=env` and is a child of the host span
`summarise_notes` (service `agent-sdk-host`), so the host span, the interaction, its three model requests and the
tool call are one trace. One of the model requests has `query_source_safe=generate_session_title`; Agent SDK
sessions send it alongside the query. The session's spans report `app.version` 2.1.286, the CLI the SDK bundles.

Anthropic run, seven prompts: only the first prompt produced a complete trace. For the other five headless turns
and the Agent SDK query, no `claude_code.interaction` span arrived and the first model request of the prompt had
no span. Each later `claude_code.llm_request` and `claude_code.tool` span arrived as the root of its own trace;
`tool.blocked_on_user` and `tool.execution` stayed under their `claude_code.tool`. Of the log records, only
`tool_decision` carried a trace id on those prompts, and the Agent SDK session's records carried the host trace
id from `TRACEPARENT`. Every `api_request` event was present, so metrics and events were complete. An Ollama
run made afterwards with the same config directory was intact. Not reproduced on Ollama, including with
`CLAUDE_CODE_PROPAGATE_TRACEPARENT=1`. One run; the cause is not established.

## Metrics

Instrumentation scope `com.anthropic.claude_code`. All are monotonic sums with delta temporality.

| Metric | Unit | Attributes |
| --- | --- | --- |
| `claude_code.session.count` | none | `start_type` (fresh, resume) |
| `claude_code.token.usage` | tokens | `type` (input, output, cacheRead, cacheCreation), `model`, `query_source` (main, auxiliary); `effort` on the Ollama run only |
| `claude_code.cost.usage` | USD | `model`, `query_source` (main, auxiliary); `effort` on the Ollama run only |
| `claude_code.active_time.total` | s | `type` (cli) |
| `claude_code.lines_of_code.count` | none | `type` (added, removed), `model` |
| `claude_code.code_edit_tool.decision` | none | `decision` (accept), `source` (config), `tool_name` (Edit), `language` (Python) |

Every data point also carries `session.id`, `user.id`, `terminal.type`, `app.version`, `app.entrypoint` and the
`OTEL_RESOURCE_ATTRIBUTES` keys. `claude_code.commit.count` and `claude_code.pull_request.count` were not
exercised. `claude_code.active_time.total` has no `type=user` series in headless runs.

## Logs

Instrumentation scope `com.anthropic.claude_code.events`. One record per event. The body is the event name with
the `claude_code.` prefix, `event.name` is the name without it, and severity is unset.

| Event | Attributes beyond the standard set |
| --- | --- |
| `claude_code.user_prompt` | `prompt_length`, `prompt` and `prompt_text` (`<REDACTED>`), `message.uuid` |
| `claude_code.api_request` | `model`, `input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_creation_tokens`, `cost_usd`, `cost_usd_micros`, `duration_ms`, `ttft_ms`, `speed`, `query_source` (sdk, generate_session_title), `effort` on the Ollama run only; `request_id` and `client_request_id` on Anthropic's API |
| `claude_code.assistant_response` | `response_length`, `response` (`<REDACTED>`), `model`, `query_source`, `message.uuid`; `request_id` on Anthropic's API |
| `claude_code.tool_decision` | `decision` (accept, reject), `source` (config), `tool_name`, `tool_use_id`, `tool_source` (builtin), `tool_parameters` |
| `claude_code.tool_result` | `tool_name`, `tool_use_id`, `success` (`"true"`, `"false"`), `duration_ms`, `tool_input_size_bytes`, `tool_result_size_bytes`, `tool_parameters`, `tool_input`; `error_type` and `error` on failure |
| `claude_code.plugin_loaded` | `plugin.name`, `marketplace.name`, `plugin.scope`, `enabled_via`, `plugin_id_hash`, `has_hooks`, `has_mcp` |
| `claude_code.managed_settings_resolved` | `managed_settings.trigger`, `managed_settings.sources`, `managed_settings.source_behavior` |

The standard set is `session.id`, `user.id`, `terminal.type`, `app.version`, `app.entrypoint`, `event.name`,
`event.timestamp` and `event.sequence`, plus `prompt.id` on records written for a prompt. `plugin_loaded` and
`managed_settings_resolved` are written at start-up and mostly have no `prompt.id`. `tool_parameters` and
`tool_input` are present because `OTEL_LOG_TOOL_DETAILS=1` is set; they hold the command line and file paths.

On the Ollama run, records written during a prompt carry the trace id and span id of the span that was active. No
`claude_code.api_error` event occurred in either run. Several numeric fields on `tool_result` and `user_prompt`
(`duration_ms`, `prompt_length`, the size fields) arrive as strings.

## Documented, not exercised

Names from Anthropic's monitoring reference that neither run produced: the metrics `claude_code.commit.count`
and `claude_code.pull_request.count`, and the events `claude_code.api_error`,
`claude_code.api_retries_exhausted`, `claude_code.mcp_server_connection` and
`claude_code.permission_mode_changed`.

## Gaps on 2.1.289

- **`claude_code.*` names, not GenAI spans.** No `gen_ai.operation.name`, no `chat {model}` or `execute_tool`
  span names, no `gen_ai.usage.*`, no `gen_ai.conversation.id` and no `gen_ai.tool.name`. The `gen_ai.*`
  attributes present are `gen_ai.system`, `gen_ai.request.model`, `gen_ai.response.id`,
  `gen_ai.response.finish_reasons` and `gen_ai.tool.call.id`.
- **`gen_ai.system`, not `gen_ai.provider.name`.** The value is `anthropic` on every model request, including
  requests served by Ollama.
- **No GenAI metrics.** `gen_ai.client.token.usage` and `gen_ai.client.operation.duration` are absent. There is
  no latency histogram; request duration is on the `api_request` event and the `llm_request` span.
- **Cost on a model Claude Code does not recognise.** `claude_code.cost.usage` and `cost_usd` are non-zero on
  the Ollama run. The CLI prices the unrecognised model at a rate of its own, so the value is not the cost of
  the local model.
- **Identity with an API key.** `user.email`, `user.account_uuid` and `organization.id` are absent. Only the
  anonymous `user.id` is present.
- **Cache tokens.** On the Anthropic run every request had `cache_read_tokens` and `cache_creation_tokens` of
  zero; prompts of the size `--bare` sends were not cached. On the Ollama run `cache_read_tokens` was non-zero.
- **Trace structure on Anthropic's API.** See Traces. After the first prompt, no interaction span and no shared
  trace. One run, cause not established.
- **Session title request.** An Agent SDK session sends a `generate_session_title` request with the query. On
  Ollama it waits in the same single slot as the query; without an output cap it asks for 32000 tokens.

## Scout export

Collector self-metrics after both runs: `otlp_http/b14` sent spans, metric points and log records with no send
failures.
