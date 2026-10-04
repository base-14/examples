# observed-telemetry.md - codex

live-captured 2026-10-04T16:13Z without the collector filter and 2026-10-04T16:16Z with it, on local Ollama

## Run context

- **Monitored software**: OpenAI Codex CLI 0.160.0 on macOS (arm64), run headless with `codex exec --json`
  through `npx -y @openai/codex@0.160.0`. Telemetry is set in `config.toml` under `CODEX_HOME`: `otel.exporter`,
  `otel.trace_exporter` and `otel.metrics_exporter` all `otlp-http` with `protocol = "binary"` to
  `localhost:4318`, `otel.environment = "dev"`, `otel.log_user_prompt = false`.
- **Model**: local Ollama 0.34.2 through Codex's built-in `ollama` provider (`model_provider = "ollama"`) on
  `qwen3.5-32k`, which is `qwen3.5:9B` with `num_ctx` 32768. No `OPENAI_API_KEY` in the environment.
  `approval_policy = "never"`, `sandbox_mode = "workspace-write"`.
- **Collector**: `otel/opentelemetry-collector-contrib:0.161.0`, OTLP receiver, debug exporter (verbosity detailed)
  and `otlp_http/b14` to Scout with `oauth2client`. The second run adds a `filter` processor on logs that drops
  `codex.sse_event` records other than `response.completed`.
- **Traffic driver**: `scripts/drive.sh`, seven headless turns in a scratch workspace: two turns in one thread
  (`codex exec`, then `codex exec resume <thread>`), one that runs `ls`, one that edits a file, one that runs
  `cat missing.txt`, one that runs `touch` under `--sandbox read-only`, and one started with `TRACEPARENT` set.

## Resource

`service.name=codex_exec`, `service.version=0.160.0`, `env=dev` (from `otel.environment`),
`telemetry.sdk.language=rust`. The log resource adds `host.name`; the metrics resource adds `os` and
`os_version`. Scopes: `codex_exec` for spans, `codex` for metrics, `codex_otel.log_only` for event records, and
`codex_otel::metrics::client` and `codex_otel::trace_context` for the `DEBUG` records.

## Traces

Codex exports its internal tracing spans. Span names are Rust function and RPC method names, not GenAI
operations. Each `codex exec` turn produces several traces:

```text
turn/start                               SERVER    rpc.system=jsonrpc, rpc.method=turn/start
└─ op.dispatch.turn_input                INTERNAL
   └─ session_task.turn                  INTERNAL  turn.id, model, codex.turn.token_usage.*
      └─ session_task.run > run_turn     INTERNAL
         └─ run_sampling_request         INTERNAL  one per model request; turn_id, model, cwd
            └─ try_run_sampling_request  INTERNAL
               ├─ stream_request > model_client.stream_responses_api  model, wire_api, transport, api.path
               └─ receiving_stream > handle_responses                 one per stream event
                  └─ handle_output_item_done > handle_tool_call_with_source
                     └─ exec_command or apply_patch                   one per tool call; tool_name, call_id
thread/start or thread/resume            SERVER    its own trace
codex.exec                               INTERNAL  its own trace; turn.id
initialize, thread/read, thread/unsubscribe        SERVER, their own traces
auth, fs.read_file, recommended_plugins_mode_for_config   single-span root traces, many per turn
list_models, session_loop, load_with_cli_overrides        small root traces of their own
```

- The seven turns of the first run produced 8177 spans in 182 traces, and 82 of the root spans were `auth`.
  Most spans are `fs.get_metadata`, `append_items`, `persist_rollout_items` and similar internals.
- `handle_responses` is one span per stream event. The last one of each model request carries
  `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`,
  `gen_ai.usage.cache_read.input_tokens`, `gen_ai.usage.cache_write.input_tokens`,
  `codex.usage.reasoning_output_tokens`, `codex.usage.total_tokens` and `codex.request.reasoning_effort`.
- `session_task.turn` carries `turn.id`, `model`, `codex.turn.reasoning_effort` and
  `codex.turn.token_usage.input_tokens`, `.cached_input_tokens`, `.cache_write_input_tokens`,
  `.non_cached_input_tokens`, `.output_tokens`, `.reasoning_output_tokens` and `.total_tokens`.
- Every span also carries `code.file.path`, `code.module.name`, `code.line.number`, `busy_ns`, `idle_ns`,
  and `thread.id` and `thread.name`, which are the operating system thread (`2`, `codex-main`), not the Codex
  thread. The Codex thread id is on events as `conversation.id`. On spans it appears only as `thread_id` on
  `session_loop`, `shell_snapshot` and `apply_rollout_reconstruction`, and as `conversation.id` on
  `unified_exec.exec_command`.
- Most log events also appear as span events on the span that was active, named after their source location,
  such as `event otel/src/tool_result.rs:54`. `codex.sse_event` and `codex.tool_decision` do not. Two span
  events, `codex.tool_call_received` and `codex.tool_result_ready`, have no log record.
- Every span has status `Unset`, including `exec_command` for the command that exited non-zero.
- With `TRACEPARENT` set in the environment, Codex logs `TRACEPARENT detected; continuing trace from parent
  context` and the turn's `turn/start`, `thread/start`, `codex.exec`, `initialize`, `thread/read` and
  `thread/unsubscribe` spans become children of the given span, in the given trace. The single-span `auth` and
  `fs.read_file` traces stay separate.

## Metrics

46 metrics per drive run, all with delta temporality. Sums have no unit; duration histograms have unit `ms`. Most carry
`app.version`, `model`, `originator` (`codex_exec`) and `session_source` (`exec`). None carries a user,
conversation or thread id.

| Metric | Type | Attributes beyond the common set |
| --- | --- | --- |
| `codex.api_request` | Sum | `status` (200), `success` |
| `codex.api_request.duration_ms` | Histogram | `status`, `success` |
| `codex.sse_event` | Sum | `kind`, `success` |
| `codex.sse_event.duration_ms` | Histogram | `kind`, `success` |
| `codex.turn.e2e_duration_ms` | Histogram | none |
| `codex.turn.ttft.duration_ms` | Histogram | none |
| `codex.turn.ttfm.duration_ms` | Histogram | none |
| `codex.turn.token_usage` | Histogram | `token_type` (input, cached_input, cache_write_input, output, reasoning_output, total), `tmp_mem_enabled` |
| `codex.turn.tool.call` | Histogram | `tmp_mem_enabled` |
| `codex.turn.memory` | Sum | `config_use_memories`, `feature_enabled`, `has_citations`, `read_allowed` |
| `codex.turn.network_proxy` | Sum | `active`, `tmp_mem_enabled` |
| `codex.turn.unified_exec.running_processes` | Sum | none |
| `codex.tool.call` | Sum | `tool`, `success`, `command_category`, `sandbox` (seatbelt), `sandbox_policy` |
| `codex.tool.call.duration_ms` | Histogram | as `codex.tool.call` |
| `codex.tool.unified_exec` | Sum | `tty` |
| `codex.conversation.turn.count` | Sum | none |
| `codex.thread.started` | Sum | `is_git`, `is_worktree` |
| `codex.process.start` | Sum | `originator` only |
| `codex.startup.phase.duration_ms` | Histogram | `phase`, `status` |
| `codex.shell_snapshot`, `codex.shell_snapshot.duration_ms` | Sum, Histogram | `success`, `version` |
| `codex.thread.skills.enabled_total`, `.kept_total`, `.truncated`, `.description_truncated_chars` | Histogram | `catalog_surface` |
| `codex.skills.shadow_selection` and its `.duration_ms`, `.catalog_entries`, `.query_terms`, `.reduction_bps`, `.selected_entries` | Sum, Histogram | `method`, `candidate_set_truncated` |
| `codex.sqlite.init.count`, `codex.sqlite.init.duration_ms` | Sum, Histogram | `db`, `phase`, `error` |
| `codex.db.backfill`, `codex.db.backfill.duration_ms` | Sum, Histogram | `status` |
| `codex.rollout.size_bytes` | Histogram | none |
| `codex.rollout_compression.materialize`, `.read`, `.read.io_duration_ms` | Sum, Histogram | `outcome`, `format` |
| `codex.thread_history.sqlite_projection` | Sum | `outcome` |
| `codex.plugins.loaded_cache.request`, `.load.duration_ms`, `.wait.duration_ms` | Sum, Histogram | `outcome` |
| `codex.plugins.startup_sync`, `codex.plugins.startup_sync.final` | Sum | not recorded |
| `codex.cloud_config_bundle.load`, `codex.cloud_config_bundle.fetch.duration_ms` | Sum, Histogram | `outcome`, `trigger`, `bundle_shape` |
| `codex.remote_models.load_cache.duration_ms` | Histogram | none |

`codex.plugins.startup_sync` and `codex.plugins.startup_sync.final` appeared in the first probe turn and not in
the drive runs.

## Logs

One record per event, severity `INFO`, empty body. The event is in `event.name`.

| Event | Attributes beyond the standard set |
| --- | --- |
| `codex.conversation_starts` | `provider_name`, `approval_policy`, `sandbox_policy`, `reasoning_summary`, `mcp_servers`, `auth.env_openai_api_key_present` and three more `auth.env_*` flags |
| `codex.user_prompt` | `prompt_length`, `prompt` (`[REDACTED]`) |
| `codex.api_request` | `duration_ms`, `http.response.status_code`, `attempt`, `endpoint` (`/responses`), `auth.header_attached`, `auth.retry_after_unauthorized` |
| `codex.sse_event` | `event.kind`, `duration_ms`; on the `response.completed` that ends a model request also `input_token_count`, `output_token_count`, `cached_token_count`, `cache_write_token_count`, `reasoning_token_count`, `tool_token_count`, `ttft_ms` |
| `codex.turn_ttft` | `duration_ms` |
| `codex.tool_decision` | `tool_name`, `tool_namespace`, `call_id`, `decision` (approved), `source` (Config) |
| `codex.tool_result` | `tool_name`, `tool_namespace`, `call_id`, `duration_ms`, `success`, `output`, `output_truncated`, `arguments`, `agent_name`, `tool_result_seq`, `mcp_server`, `mcp_server_origin` |
| `codex.sandbox_outcome` | `tool_name`, `call_id`, `outcome` (denied), `initial_duration_ms` |
| `codex.startup_phase` | `startup.phase`, `startup.status`, `duration_ms` |

The standard set is `conversation.id`, `model`, `slug`, `app.version`, `originator`, `terminal.type`,
`event.name` and `event.timestamp`. `conversation.id` is the thread id that `codex exec --json` prints, and a
resumed thread keeps it. Event records carry the trace id and span id of the active span, except
`codex.sse_event`, which carries none.

- `codex.sse_event` is written once per stream chunk: 568 of 635 records in the unfiltered run. With the
  collector filter, 28 remain, all `response.completed`.
- Two `response.completed` records are written per model request. One carries the token counts.
- `tool_token_count` equals `codex.usage.total_tokens` on the request sampled.
- `codex.tool_result` holds content with `log_user_prompt` off: `arguments` is the full command line, or the
  patch body for `apply_patch`, and `output` is the command's output, including file contents it printed.
- On log records, `duration_ms`, `prompt_length`, `input_token_count`, `output_token_count` and
  `tool_token_count` arrive as strings. `http.response.status_code`, `attempt`, `cached_token_count`,
  `reasoning_token_count` and `ttft_ms` are integers.
- Eight `DEBUG` records without `event.name` also arrive: `flushing OTEL metrics` once per turn, and the
  `TRACEPARENT detected` line.

## Gaps on 0.160.0

- **No GenAI span names or operations.** No `gen_ai.operation.name`, `gen_ai.request.model`,
  `gen_ai.provider.name` or `gen_ai.conversation.id`. The only `gen_ai.*` attributes are the four
  `gen_ai.usage.*` keys on `handle_responses`.
- **No GenAI metrics.** `gen_ai.client.token.usage` and `gen_ai.client.operation.duration` are absent. Tokens
  are in `codex.turn.token_usage`.
- **No cost.** No metric, span or event carries a cost.
- **Several traces per turn, and internal spans.** See Traces. `auth` and file reads arrive as single-span
  traces.
- **`success` on `codex.tool_result` is not the command's exit status.** It is `true` for `cat missing.txt`,
  which exits non-zero, and for the `touch` the read-only sandbox denied. It is `false` for an `apply_patch`
  call that Codex rejected. The sandbox denial is in `codex.sandbox_outcome`.
- **No span status.** Every span is `Unset`.
- **`provider_name` on Ollama is `gpt-oss`**, not `ollama`.
- **No identity.** No user or account attribute on any signal in a run without OpenAI authentication.
- **`--oss` pulls a model.** `codex exec --oss` ignores `model` in `config.toml` and starts downloading
  `gpt-oss:20b` into Ollama. The rig sets `model_provider = "ollama"` in the config instead.

## Scout export

Collector self-metrics after the run: `otlp_http/b14` sent spans, metric points and log records with no send
failures.
