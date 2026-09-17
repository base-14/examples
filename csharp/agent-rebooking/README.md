# Approval-Gated Rebooking Agent (C#) - Microsoft Agent Framework + MCP + OpenTelemetry

A travel disruption agent on .NET 10 and Microsoft Agent Framework 1.21. A triage agent hands off
to a rebooking agent, the rebooking tools come from an in-process MCP server, and a rebooking over
a price limit waits for a human before it runs. One trace covers the handoff, the MCP client and
server, the database work and the approval.

The model runs on a local Ollama. Telemetry goes to an OpenTelemetry Collector, which forwards it
to base14 Scout.

> [Full documentation](https://docs.base14.io/guides/ai-observability/agent-approval-gates/)

## Prerequisites

### base14 Scout credentials are required to run the stack

The collector in `compose.yaml` authenticates to Scout with the `oauth2client` extension, and that
extension validates its configuration at startup. With the four values empty, as `.env.example`
ships them, the collector exits immediately:

```text
Error: invalid configuration: extensions::oauth2client: no ClientID provided in the OAuth2 exporter configuration
```

There is no credential-free local mode. `make up` brings up Postgres and the app, the collector
container exits, and nothing is exported. If you see that line in `docker compose logs
otel-collector`, fill in the four variables below.

| Variable | What it is |
| --- | --- |
| `SCOUT_CLIENT_ID` | OAuth2 client id for your Scout tenant. |
| `SCOUT_CLIENT_SECRET` | OAuth2 client secret. |
| `SCOUT_TOKEN_URL` | Token endpoint, for example `https://your-tenant.base14.io/oauth/token`. |
| `SCOUT_ENDPOINT` | OTLP/HTTP endpoint the collector exports to. |

Put them in `.env` next to `compose.yaml`, or export them in the shell you run `make up` from. A
fifth variable, `SCOUT_ENVIRONMENT`, sets `deployment.environment` and `environment` on every
resource and defaults to `development`.

```bash
cp .env.example .env
# fill in SCOUT_CLIENT_ID, SCOUT_CLIENT_SECRET, SCOUT_TOKEN_URL, SCOUT_ENDPOINT
```

The four values ship empty rather than as `your-client-id` style placeholders. A filled-in
placeholder passes the collector's own validation, so the collector starts, reports healthy, and
then fails every export against a tenant that does not exist. Empty, you get the error above.

Copy the file, fill in those four values, and `make up` works. Change nothing else in it. `.env` is
the file Compose itself reads for interpolation, so any other value set there wins over the default
in `compose.yaml` and lands inside the containers. Two variables therefore ship commented out,
`POSTGRES_CONNECTION_STRING` and `OTEL_EXPORTER_OTLP_ENDPOINT`: the values written next to them are
the host-side ones, correct for running the app outside Compose and wrong inside a container, where
`localhost` is the container. Compose supplies the in-network values on its own.

### Everything else

- Docker with Compose v2.
- .NET SDK 10.0.400 for `make ci`. `global.json` pins it; the Compose build uses the SDK image and
  needs no local install.
- Ollama on the host, with the model pulled before the first run.

```bash
ollama pull qwen3.5:9b
```

Ollama runs on the host rather than in Compose, because there is no GPU inside Docker on macOS. The
app reaches it through `host.docker.internal:11434`.

## How to instrument an agent-framework app with OpenTelemetry

1. Name every activity source and meter in one place and register them there.
   `Telemetry/Sources.cs` holds four names: the example's own `AgentRebooking`,
   `Experimental.Microsoft.Agents.AI`, `Experimental.ModelContextProtocol` and `Npgsql`.
   `Telemetry/TelemetryRegistration.cs` is the only file that hands those lists to a provider
   builder, and the tests call it too, so a source that stops being registered also stops being
   asserted on.
2. Wrap each agent with `UseOpenTelemetry`. `Agents/AgentSetup.cs` builds both agents with
   `.AsBuilder().UseOpenTelemetry(configure: ...).Build()`. At 1.21.0 the agent-level call also
   activates chat-client telemetry under the same source, so `invoke_agent`, `chat` and
   `execute_tool` spans all come from that one call.
3. Register `Experimental.ModelContextProtocol` before the MCP session opens. The MCP C# SDK checks
   `ActivitySource.HasListeners()` on that exact name before it instruments anything. Without a
   listener the `execute_tool` span loses every `mcp.*` attribute and `params._meta` loses
   `traceparent`, with no error and no log line. `Program.cs` registers `AgentToolProvider` as a
   hosted service after `AddOpenTelemetry()` so the session starts after the listeners exist.
4. Create the custom `Meter` with the same name that `AddMeter` registers. `Program.cs` registers
   `new Meter("AgentRebooking")` and `TelemetryRegistration` calls `AddMeter("AgentRebooking")`.
   `AddMeter` matches by name, not by instance, and a mismatch drops the measurements silently.
5. Carry the run's `ActivityContext` across the approval. `Runs/RunStore.cs` captures the root
   context when a run starts and passes it as the explicit parent of `base14.agent.run` and
   `base14.agent.resume`. The approval answer arrives on a different HTTP request, so without this
   the post-approval work lands in the approver's trace.
6. Export OTLP to the collector. `Program.cs` calls `UseOtlpExporter()` when
   `OTEL_EXPORTER_OTLP_ENDPOINT` is set and skips it when it is not, so the app also runs
   standalone without connection-refused noise.

## Stack profile

| Component | Version | Notes |
| --- | --- | --- |
| .NET SDK | 10.0.400 | `global.json` and `.tool-versions`. |
| ASP.NET Core | 10.0 | Minimal APIs. |
| `Microsoft.Agents.AI.Workflows` | 1.21.0 | Handoff builder. |
| `Microsoft.Agents.AI.OpenAI` | 1.21.0 | OpenAI provider. |
| `Microsoft.Agents.AI.Anthropic` | 1.21.0-preview.260911.1 | Prerelease, exact pin. |
| `Microsoft.Extensions.AI` | 10.10.0 | `ApprovalRequiredAIFunction`, chat telemetry. |
| `ModelContextProtocol` | 2.2.0 | Client, server and in-process transport. |
| `OllamaSharp` | 5.4.30 | Default provider path. |
| `Npgsql` | 10.0.3 | Tool storage. |
| `OpenTelemetry.*` | 1.18.0 | SDK, OTLP exporter, ASP.NET Core, HttpClient, Runtime. |
| PostgreSQL | `postgres:18-alpine` | Published on host port **5433**. |
| OTel Collector contrib | 0.158.0 | oauth2client, otlp_http to Scout, debug to stdout. |
| Ollama model | `qwen3.5:9b` | On the host, not in Compose. |

**Verified**: 2026-09-16.

Postgres is published on 5433 rather than 5432 to avoid colliding with a Homebrew Postgres. Inside
Compose the app still connects on 5432.

## What's instrumented

- ASP.NET Core HTTP server spans (auto).
- HttpClient spans for the calls to Ollama (auto). They appear as `POST` under each `chat` span.
- Npgsql spans for the tool queries (auto, listener only).
- Agent framework spans: `invoke_agent {Name}({Id})`, `chat {model}`, `execute_tool {tool}`.
- MCP SDK spans: `server/discover`, `tools/list` and the `tools/call {tool}` server span.
- The example's own spans: `base14.agent.run`, `base14.agent.resume`,
  `base14.approval.requested {tool}`, `base14.approval.decided {tool}`.
- The example's own metrics: `base14.agent.approval.wait.duration`, `base14.agent.approval.count`,
  `base14.gen_ai.error.count`.
- Structured logs through the OpenTelemetry logging provider, with trace and span id on every
  record.

## Architecture

```text
+------------------+      +-------------------------------------------+
| curl / scripts   |----->| app (ASP.NET Core, :8080)                 |
| POST /runs       |      |                                           |
| POST /approvals  |      |  triage agent --handoff--> rebooking agent|
+------------------+      |         |                       |         |
                          |         |            MCP client |         |
                          |         |                       v         |
                          |         |            MCP server (in proc) |
                          +---------|-----------------------|---------+
                                    |                       |
                  OLLAMA_BASE_URL   |                       | Npgsql
                                    v                       v
                        +----------------------+   +------------------+
                        | Ollama on the host   |   | PostgreSQL 18    |
                        | qwen3.5:9b :11434    |   | host :5433       |
                        +----------------------+   +------------------+

        app --OTLP/HTTP :4318--> otel-collector --oauth2--> base14 Scout
                                        |
                                        +--> debug exporter (stdout)
```

The MCP client and server run in the same process over a pair of in-memory pipes. One session lives
for the process lifetime.

## Running it

```bash
cd csharp/agent-rebooking
cp .env.example .env     # fill in the four SCOUT_* variables first
ollama pull qwen3.5:9b

make up                  # docker compose up -d --build
make logs                # follow all three containers
```

Check that all three containers are up before driving the API:

```bash
docker compose ps
curl -s http://localhost:8080/health
```

Drive one run by hand:

```bash
curl -s -X POST http://localhost:8080/runs \
  -H 'content-type: application/json' \
  -d '{"message":"My flight to Berlin was cancelled. My booking is BK-1001."}'

curl -s http://localhost:8080/runs/run-xxxxxxxxxxxx
```

Other targets:

```bash
make ci                          # check + build-lint + test, no stack needed
make test-api                    # eight API cases, roughly six minutes
SKIP_FAILURE_CASES=1 ./scripts/test-api.sh   # the two happy-path cases only, roughly 80s
make verify-scout                # telemetry assertions, roughly nine minutes
make down                        # stop, keep the Postgres volume
make reset                       # stop and drop the volume, so Seed.sql runs again
```

The three timings above are approximate and move with model speed. `make test-api` and
`make verify-scout` both need a running stack and a local Ollama, so `make ci` leaves them out.
Both restart the app service while driving the failure cases and put the stack back from an `EXIT`
trap. Neither touches Ollama.

### Running the app outside Compose

`dotnet run` against the Compose Postgres works with nothing exported: the app's built-in default
is already `Host=localhost;Port=5433`, the published port. The app does not read `.env` at all, so
export what you need in the shell instead.

```bash
make up                                                   # postgres and the collector
docker compose stop app
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318  # unset skips the exporter
dotnet run --project AgentRebooking
```

Do not uncomment either line in `.env`. Compose reads that file, and both values are wrong inside a
container.

## API endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/runs` | Start a run from a traveller message. Returns `202` with the run id. |
| GET | `/runs/{runId}` | State, outcome, reply, tool call log, approvals. |
| GET | `/approvals` | Pending approvals across all runs. |
| POST | `/approvals/{approvalId}` | Answer one approval with `{"approved": true}` or `false`. |
| GET | `/health` | Liveness for Compose and the scripts. |

Run states are `running`, `pending_approval`, `completed` and `failed`. `outcome` is `auto`,
`approved`, `rejected` or `expired`. `reply` carries the agent's final text when the model produced
one and is null when it did not, including on runs that reach `completed`.

## Seed data

| Booking | Route and date | Alternatives | Hotel | Case |
| --- | --- | --- | --- | --- |
| `BK-1001` | LHR to BER, 2026-10-02 | `FL-201` (180), `FL-202` (240) | Berlin (120) | Under the limit. The gate auto-approves. |
| `BK-1002` | LHR to JFK, 2026-10-02 | `FL-301` (620), `FL-302` (710) | New York (210) | Over the limit. The run parks. |
| `BK-1003` | LHR to CDG, 2026-10-03 | `FL-401` (95) | Paris (140) | Under the limit, one option. |

Every alternative for a booking sits on one side of `APPROVAL_LIMIT` (default 300), so the test
outcome depends on the seed data rather than on which option the model picks. `make reset` is
needed after editing `Data/Seed.sql`; the seed only inserts rows that are not already there.

## The trace

One trace per traveller message, rooted at the `POST /runs` request. This tree was read out of the
collector log for trace `a27b0b78887278f1e45eae486ae8ca15`, a `BK-1002` run that parked on an
approval and was approved:

```text
POST /runs
  base14.agent.run
    invoke_agent triage(triage)
      chat qwen3.5:9b
        POST                                (HttpClient to Ollama)
    invoke_agent rebooking(rebooking)
      chat qwen3.5:9b
        POST
      execute_tool lookup_booking
        tools/call lookup_booking           (MCP server span)
          CONNECT agentrebooking
          postgresql
      chat qwen3.5:9b
        POST
      execute_tool search_alternatives
        tools/call search_alternatives
          postgresql
          postgresql
      chat qwen3.5:9b
        POST
    postgresql                              (the gate's own price lookup)
    base14.approval.requested rebook
    invoke_agent rebooking(rebooking)       (the pass after the approval)
      execute_tool rebook
        tools/call rebook
          postgresql
      chat qwen3.5:9b
        POST
  base14.agent.resume

POST /approvals/{approvalId}                (a separate trace)
  base14.approval.decided rebook            (links to base14.approval.requested)

server/discover, tools/list                 (MCP client and server pairs, in a startup trace)
```

Four details in that tree:

**The pass after the approval parents to `base14.agent.run`, not to `base14.agent.resume`.** The
workflow's executors run on the `ExecutionContext` captured when
`InProcessExecution.RunStreamingAsync` was called, which is inside `base14.agent.run`. The ambient
activity at resume time has no influence on where those spans land. `base14.agent.resume` anchors
the spans the run store itself opens during a resume and measures the post-approval pass; on a
single-approval run it has no children.

**There is no `execute_tool` span for the handoff.** The handoff tool is a declaration with no
body, so the function-invoking chat client never runs it. Read the handoff from the pair of
`invoke_agent` spans, and from `gen_ai.tool.definitions` on the triage span, which lists the handoff
tool.

**The injected handoff tool is named `handoff_to_1`**, a one-based counter over the source agent's
targets. The framework's documentation says `handoff_to_<agent_id>`, which is not what 1.21.0 emits.
It appears in `toolCalls` on `GET /runs/{runId}`.

**There is no separate MCP client span for `tools/call`.** The C# SDK finds the outer `execute_tool`
activity, puts the `mcp.*` attributes on it, and parents the server span to it. `server/discover`
and `tools/list` do get their own client spans, because no outer tool span exists for them. Across
the collector window used here, all 162 `tools/call` server spans were parented to an `execute_tool`
span.

An `execute_tool` span therefore carries both attribute sets:

```text
gen_ai.operation.name: execute_tool
gen_ai.tool.type: function
gen_ai.tool.call.id: 57bc27b2
gen_ai.tool.name: lookup_booking
gen_ai.tool.description: Look up a booking by its reference and return its route, date and status.
mcp.session.id: 315342e5243f4e3da9a5d5a7229abc62
jsonrpc.request.id: 3
mcp.method.name: tools/call
network.transport: pipe
mcp.protocol.version: 2026-07-28
```

## MCP trace context

`ModelContextProtocol.Core` 2.2.0 injects `traceparent` into `params._meta` on every request, and
the server uses it as the parent of the server span. Nothing in this example writes that; it comes
from the SDK. This `_meta` was printed on the server inside `lookup_booking` during the Task 2
spike, recorded in `SPIKE-FINDINGS.md`:

```json
{
  "io.modelcontextprotocol/protocolVersion": "2026-07-28",
  "io.modelcontextprotocol/clientInfo": {"name": "Spike", "version": "1.0.0.0"},
  "io.modelcontextprotocol/clientCapabilities": {},
  "traceparent": "00-7019c0b8ac60c9ea8f26ecf0b55c8e17-456ad30fe6f2d933-01"
}
```

`456ad30fe6f2d933` is the span id of that run's `execute_tool lookup_booking` span, and the
`tools/call lookup_booking` server span's parent is the same id. `tracestate` is absent because
nothing set one.

The app never prints `_meta` itself, so the equivalent check on this example is the parentage: every
`tools/call` server span in the collector log has an `execute_tool` span as its parent.
`AgentRebooking.Tests/TelemetryTests.cs` asserts that parentage, so dropping the
`Experimental.ModelContextProtocol` registration fails a test instead of silently removing the hop.

## The approval gate

`rebook` and `add_hotel` are wrapped in `ApprovalRequiredAIFunction`, so the workflow pauses on
every call to them. The app's handler reads the flight or hotel id out of the call, looks the price
up in Postgres, and compares it with `APPROVAL_LIMIT`. The price the model wrote is never trusted.
Under the limit the handler answers yes at once and the run carries on. Over the limit, or when the
id is unknown, the run becomes `pending_approval`.

Two short spans and two instruments carry this, instead of one span held open for minutes:

| Span | Where it lives | Attributes |
| --- | --- | --- |
| `base14.approval.requested {tool}` | The traveller's trace, under `base14.agent.run`. | `gen_ai.tool.name`, `base14.run.id`, `base14.approval.amount`, `base14.approval.limit`. |
| `base14.approval.decided {tool}` | The approver's `POST /approvals/{id}` trace, or no trace at all on expiry. | The four above plus `base14.approval.outcome` and `base14.approval.wait_seconds`. |

The decided span carries an `ActivityLink` back to the requested span. A link carries only a trace
id and a span id, which is why `base14.run.id` is on both spans: it is the only attribute on the
decided span that says which run the decision belongs to.

An approval measured on 2026-09-16, from the collector log:

```text
Span   base14.approval.decided rebook
Trace  82368594264c4662b62157c4be290a8a
  gen_ai.tool.name: rebook
  base14.run.id: run-e8e49764fd79
  base14.approval.limit: 300
  base14.approval.amount: 620
  base14.approval.outcome: approved
  base14.approval.wait_seconds: 0.7895599
Links:
  Trace ID a27b0b78887278f1e45eae486ae8ca15, Span ID 4dec44def9472697
```

The histogram records the same wait. Bucket boundaries are set with a view in
`TelemetryRegistration` and are human-scale rather than the SDK defaults:

```text
base14.agent.approval.wait.duration   Histogram, unit s
  Data point attributes:
    base14.approval.outcome: expired
    gen_ai.tool.name: rebook
  Count: 1   Sum: 13.997132
  Bounds: 1, 5, 15, 30, 60, 120, 300, 600, 900
```

`base14.agent.approval.count` counts the same decisions by tool and outcome. An auto-approved call
gets no span, only a counter point with outcome `auto`.

## Telemetry reference

### Resource attributes

Exported on every signal:

```text
service.name: agent-rebooking
service.namespace: examples
deployment.environment: <SCOUT_ENVIRONMENT>
environment: <SCOUT_ENVIRONMENT>
telemetry.sdk.name: opentelemetry
telemetry.sdk.language: dotnet
telemetry.sdk.version: 1.18.0
```

Both `deployment.environment` and `environment` are set, by the app and again by the collector's
`resource` processor.

### Metrics seen in a live run

| Metric | Source |
| --- | --- |
| `gen_ai.client.operation.duration` | Agent framework. |
| `gen_ai.client.token.usage` | Agent framework. |
| `gen_ai.client.operation.time_to_first_chunk` | Agent framework, streaming. |
| `gen_ai.client.operation.time_per_output_chunk` | Agent framework, streaming. |
| `mcp.client.operation.duration` | MCP SDK. |
| `mcp.server.operation.duration` | MCP SDK. |
| `base14.agent.approval.wait.duration` | This example. |
| `base14.agent.approval.count` | This example. |
| `base14.gen_ai.error.count` | This example, on a failed model call. |
| `db.client.*`, `received-first-response` | Npgsql. |
| `http.server.*`, `http.client.*`, `kestrel.*`, `aspnetcore.*` | ASP.NET Core and HttpClient. |
| `dns.lookup.duration` | `System.Net.NameResolution`. |
| `dotnet.*` | .NET runtime instrumentation. |

There is no `gen_ai.execute_tool.duration` instrument at 1.21.0, so the MCP client duration is not
double counted.

`base14.gen_ai.cost`, `base14.gen_ai.retry.count` and `base14.gen_ai.fallback.count` are emitted by
`GatewayChatClient` on the non-streaming path only. The agent framework streams, so these three stay
at zero in a live run of this example and only the unit tests exercise them. `base14.gen_ai.error.count`
is counted on the streaming path as well.

### Content capture

`OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT` defaults to `false`. Prompts and replies carry
traveller data, and a backend keeps whatever is exported.

With it set to `true`, measured on a live `BK-1001` run on 2026-09-16:

| Span | `gen_ai.input.messages` | `gen_ai.output.messages` | `gen_ai.system_instructions` |
| --- | --- | --- | --- |
| `chat qwen3.5:9b` (all four) | yes | yes | yes |
| `invoke_agent triage(triage)` | yes | yes | yes |
| `invoke_agent rebooking(rebooking)` (both) | yes | yes | no |
| `execute_tool {tool}` | no | no | no |
| `tools/call {tool}` | no | no | no |

The framework writes these as span attributes, not events, and the same messages appear twice: once
on the agent span and once on the chat span below it. `gen_ai.system_instructions` was present on
the triage agent span and absent from both rebooking agent spans, in this run and in the spike run
that first recorded it. Why it differs by agent has not been tested.

### Workflow spans

`Microsoft.Agents.AI.Workflows` is deliberately not registered. Its spans are gated behind
`WorkflowBuilder.WithOpenTelemetry`, which the handoff builder does not expose at 1.21.0, so
registering the source would add a name that can never produce a span.

## Error matrix

Six failure scenarios, each driven against the live stack on 2026-09-16 with `qwen3.5:9b` on the
host. Every trace id below is from that session. `scripts/verify-scout.sh` drives all six on each
run and asserts the telemetry named here.

| Scenario | Trigger | What carries the failure | Run state | Trace |
| --- | --- | --- | --- | --- |
| Run timeout | `RUN_TIMEOUT_SECONDS=5` | `base14.agent.run` Error, plus an ERROR log record | `failed` | `d6207cca60fefd2626958ce089026e5d` |
| Model unreachable | `OLLAMA_BASE_URL` on a dead port | `chat {model}`, `invoke_agent triage(triage)` and `base14.agent.run` all Error; `base14.gen_ai.error.count` | `failed` | `d59718e2306d2579a0400c7ffe9356c2` |
| Unknown booking | ask about `BK-9999` | `tools/call lookup_booking` and `execute_tool lookup_booking` Error; the run stays Unset | `completed` | `974a88eb44b741ff1186f64816476fb5` |
| Database unreachable | `docker compose stop postgres` | Npgsql spans Error, `execute_tool` and `tools/call` Error; the run stays Unset | `completed` | `2e04ae20bb54da4c1506e42d19fc96c7` |
| Approval rejected | answer `approved:false` | nothing. `base14.approval.outcome: rejected`, and no `execute_tool rebook` span | `completed` | `5d4a1e468131b30d460e6b3a97497f93` |
| Approval expired | `APPROVAL_TIMEOUT_SECONDS=10` | nothing. `base14.approval.outcome: expired`, and no `execute_tool rebook` span | `completed` | `ba55dbc368251203e6a0f851a579b38f` |

### Run timeout

Trace `d6207cca60fefd2626958ce089026e5d`. The sweeper fails a run that outlives
`RUN_TIMEOUT_SECONDS`. This is the one row where the app itself sets the status.

```text
base14.agent.run       Error   the run exceeded RUN_TIMEOUT_SECONDS
POST /runs             Unset
chat qwen3.5:9b        Unset
invoke_agent triage    Unset
```

The status message is a plain sentence, which is not true of the other rows. The spans below
`base14.agent.run` are Unset and some of them end after it: in this trace the run span ends at
04:44:07.476 and `execute_tool search_alternatives` ends at 04:44:17.918. Cancelling a run does not
reach an in-flight model call or MCP call straight away, so do not read the run span's duration as
the end of the run's work.

There is also an ERROR log record, `Run {RunId} failed: the run exceeded RUN_TIMEOUT_SECONDS`, with
`RunId` and `Error` as attributes. Its trace id is empty, because the sweeper runs on a timer with
no ambient activity.

### Model unreachable

Trace `d59718e2306d2579a0400c7ffe9356c2`. The app was started with `OLLAMA_BASE_URL` pointing at a
port nothing listens on. Do not stop the host's Ollama to reproduce this: it is not part of the
Compose stack.

```text
base14.agent.run                Error   executor 'triage_triage' failed: System.Net.Http.HttpRequestException: ...
invoke_agent triage(triage)     Error   Network is unreachable (host.docker.internal:11435)
chat qwen3.5:9b                 Error   Network is unreachable (host.docker.internal:11435)
POST                            Error
POST /runs                      Unset
```

This is the row where the error is visible at every level, because the failure is the model call
itself. The status message on `base14.agent.run` is a .NET stack trace several kilobytes long: the
workflow puts the exception's `ToString()` in `ExecutorFailedEvent.Data` and the run store passes it
through.

`base14.gen_ai.error.count` gets a point tagged `gen_ai.provider.name: ollama`,
`gen_ai.request.model: qwen3.5:9b` and `error.type: HttpRequestException`. `error.type` separates
a provider that is down from one that is rejecting requests.

### Unknown booking

Trace `974a88eb44b741ff1186f64816476fb5`. A failed tool call inside a run that succeeds.

```text
tools/call lookup_booking      Error   [{"type":"text","text":"An error occurred invoking \u0027lookup_booking\u0027: No booking found for reference \u0027BK-9999\u0027."}]
execute_tool lookup_booking    Error   [{"type":"text","text":"An error occurred invoking \u0027lookup_booking\u0027: No booking found for reference \u0027BK-9999\u0027."}]
base14.agent.run               Unset
```

Nothing in the app sets either status. The MCP SDK sets Error on the server span when the tool
result carries `IsError`, and the agent framework propagates it to `execute_tool`. The status
message is the serialised tool result content, a JSON array of content blocks, so a status-message
search for human-readable text will not find a sentence. The message went through
`System.Text.Json`, whose default encoder escapes apostrophes, so each one arrives as the six
characters `\u0027`. Search for `invoking` rather than for `invoking 'lookup_booking'`,
which matches nothing.

`base14.agent.run` stays Unset and the run reaches `completed`. The agent read the error, recovered
and answered the traveller. The run span carries no error status, so a filter on run status does
not return this case; the two tool spans do carry it.

### Database unreachable

Trace `2e04ae20bb54da4c1506e42d19fc96c7`. Postgres stopped under a running app.

```text
postgresql                          Error   57P01
CONNECT agentrebooking              Error   Name or service not known
execute_tool lookup_booking         Error   [{"type":"text","text":"An error occurred invoking \u0027lookup_booking\u0027."}]
tools/call lookup_booking           Error   [{"type":"text","text":"An error occurred invoking \u0027lookup_booking\u0027."}]
execute_tool search_alternatives    Error   [{"type":"text","text":"An error occurred invoking \u0027search_alternatives\u0027."}]
base14.agent.run                    Unset
```

Two Npgsql spans fail two different ways. `57P01` is `admin_shutdown` on a connection that was
already open when the database went away. `Name or service not known` is a fresh `CONNECT` failing
to resolve the host. Both in one trace means the outage started mid-run. With the database already
down when the run starts there is no command span at all, only the failing `CONNECT`, so a check on
this row has to look at both names.

The tool error message here carries no reason, unlike the unknown-booking row. The MCP server does
not put an unexpected exception's message in the result, so the cause is in the Npgsql span and
nowhere else.

The run completes and `base14.agent.run` stays Unset. `reply` comes back null on this `completed`
run.

### Approval rejected

Trace `5d4a1e468131b30d460e6b3a97497f93`. A human answered `{"approved": false}`.

Every span in the run trace is Unset. Two spans that an approved rebooking produces are not
emitted at all:

```text
execute_tool rebook     (no span)
tools/call rebook       (no span)
```

The tool never ran. `GET /runs/{id}` still lists `rebook` under `toolCalls`, because that records
the call the model asked for.

`base14.approval.decided rebook` carries `base14.approval.outcome: rejected` and
`base14.approval.wait_seconds`, sits in the approver's `POST /approvals/{id}` trace, and links back
to `base14.approval.requested rebook` in the traveller's trace. Status stays Unset on both spans,
and on every other span of the run.

### Approval expired

Trace `ba55dbc368251203e6a0f851a579b38f`. The same shape with nobody answering.
`base14.approval.outcome: expired`, everything Unset, no `execute_tool rebook` span, and the run
completes with `outcome: expired`.

One difference from the rejected row: the decided span is the root of its own trace with no parent,
because the expiry comes from the sweeper rather than from a request.

### Filtering

Filtering on `status = Error` finds the run timeout and the model outage. The unknown-booking and
database-unreachable rows leave `base14.agent.run` Unset and put the error on the tool spans, so
filter on `execute_tool` or `tools/call` status to find those. The two approval rows set no error
status anywhere; filter on `base14.approval.outcome` to find them.

A failure recorded while a run is parked on an approval marks no span. The pump span stops when the
run parks and the resume span does not start until the decision is sent, so in that window there is
no span of the run to mark. Those failures are on the run record and in an ERROR log record only.
The rule and its reasoning are written out at `RunStore.Fail`.

### Reproducing

`scripts/test-api.sh` drives all six at the API level; `scripts/verify-scout.sh` drives them again
and asserts the telemetry. Both stop Postgres once and put everything back from an `EXIT` trap.
Budget roughly five minutes for the failure section of `test-api.sh` and roughly nine minutes for
`verify-scout.sh` end to end, both approximate. `SKIP_FAILURE_CASES=1` runs `test-api.sh` without the
failure section.

Restarting the app inside the SDK's batch export period loses whatever has not gone out yet. A
run-timeout scenario whose app was restarted two seconds later kept its span and lost its ERROR log
record. `verify-scout.sh` waits `EXPORT_SETTLE_SECONDS` before each restart for that reason;
`test-api.sh` does not need to, because it asserts on the API rather than on telemetry.

## Providers

`LLM_PROVIDER` selects the chat client: `ollama` (default), `openai` or `anthropic`. `LLM_MODEL`
sets the model and `LLM_FALLBACK_PROVIDER` names a second provider for the gateway to fall back to.

The service refuses to start a hosted provider unless `ALLOW_HOSTED_PROVIDER=true`:

```text
LLM_PROVIDER is 'openai', a hosted provider, but ALLOW_HOSTED_PROVIDER is not 'true'.
Set ALLOW_HOSTED_PROVIDER=true to let the service start a hosted provider.
```

The guard runs at startup, not on the first request. Compose passes `OPENAI_API_KEY` and
`ANTHROPIC_API_KEY` through with `${VAR:-}` as the sibling examples do, so a key exported in a
developer's shell reaches the container. `ALLOW_HOSTED_PROVIDER` still has to be set before the
service starts one. Startup logs the active provider and model.

`_shared/pricing.json` at the repository root has no entry for `qwen3.5:9b`, so cost is zero on the
default path.
`base14.gen_ai.cost` is also non-streaming only, so it records nothing in a live run whichever
provider is set.

## Environment variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `LLM_PROVIDER` | `ollama` | Chat client selection. |
| `LLM_MODEL` | `qwen3.5:9b` | Model id passed to the provider. |
| `LLM_FALLBACK_PROVIDER` | empty | Second provider for the gateway. |
| `OLLAMA_BASE_URL` | `http://host.docker.internal:11434` | Host Ollama, from inside the container. |
| `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` | empty | Hosted provider keys. |
| `ALLOW_HOSTED_PROVIDER` | `false` | Must be `true` before a hosted provider starts. |
| `POSTGRES_CONNECTION_STRING` | `Host=postgres;Port=5432` in Compose, `localhost:5433` otherwise | Booking store. Commented out in `.env.example`; see above. |
| `APPROVAL_LIMIT` | `300` | Above this a rebooking waits for a human. |
| `APPROVAL_TIMEOUT_SECONDS` | `600` | An unanswered approval expires. |
| `RUN_TIMEOUT_SECONDS` | `300` | A run over this is failed by the sweeper. |
| `RUN_TTL_SECONDS` | `3600` | Finished runs are evicted after this. |
| `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT` | `false` | Prompts and replies on spans. |
| `OTEL_SERVICE_NAME` | `agent-rebooking` | `service.name`. |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://otel-collector:4318`, fixed by Compose | Unset disables the exporter. Settable only outside Compose. |
| `OTEL_EXPORTER_OTLP_PROTOCOL` | `http/protobuf` | Exporter protocol. |
| `PRICING_FILE` | `/app/pricing.json` | LLM cost table for `base14.gen_ai.cost`. Not what the approval gate prices from. |
| `SCOUT_CLIENT_ID`, `SCOUT_CLIENT_SECRET`, `SCOUT_TOKEN_URL`, `SCOUT_ENDPOINT` | empty | Required by the collector. |
| `SCOUT_ENVIRONMENT` | `development` | `deployment.environment` and `environment`. |

Anything other than a case-insensitive `true` is read as false for the two boolean variables, so a
set-but-empty value fails closed rather than throwing.

## Troubleshooting

### The collector container exits straight after `make up`

Check `docker compose logs otel-collector` for:

```text
Error: invalid configuration: extensions::oauth2client: no ClientID provided in the OAuth2 exporter configuration
```

`SCOUT_CLIENT_ID` is empty. The collector validates the `oauth2client` extension at startup and
will not run without it. Fill in the four `SCOUT_*` variables in `.env` and run `make up` again.

### Runs never leave `running`

Check that Ollama is up on the host and that the model is pulled:

```bash
curl -s http://localhost:11434/api/tags | grep qwen3.5
ollama pull qwen3.5:9b
```

From inside the container Ollama is `host.docker.internal:11434`, which Compose wires with
`extra_hosts: host.docker.internal:host-gateway`. A first cold model load adds a minute or two.

### A run completes without calling `rebook`

The model answered the traveller without using the tool. Measured at about one run in nine on
`qwen3.5:9b`. `scripts/test-api.sh` retries such a run once before failing. A larger model reduces
it.

### Postgres will not start, or the app connects to the wrong database

Port 5433 is published on the host to avoid a Homebrew Postgres on 5432. If 5433 is also taken,
change the `ports:` entry for the `postgres` service and the `Port=` in
`POSTGRES_CONNECTION_STRING`. Inside Compose the app always uses 5432 on the `postgres` service
name.

### Edits to `Seed.sql` have no effect

The seed only inserts rows that are not already there, and the volume survives `make down`. Use
`make reset`, which drops the volume.

### `verify-scout.sh` reports a missing ERROR log record

The app was probably restarted inside the SDK's batch export period. Raise
`EXPORT_SETTLE_SECONDS` and run it again.

## Project layout

```text
csharp/agent-rebooking/
+-- AgentRebooking/
|   +-- Agents/              AgentSetup (handoff workflow), AgentToolProvider (MCP session)
|   +-- Api/                 RunEndpoints
|   +-- Data/                BookingStore, Schema.sql, Seed.sql
|   +-- Llm/                 ChatClientFactory, GatewayChatClient, Pricing
|   +-- Mcp/                 McpHosting (in-process transport), RebookingTools
|   +-- Runs/                RunStore, ApprovalGate, RunModels
|   +-- Telemetry/           Sources, TelemetryRegistration, ApprovalTelemetry
|   +-- Program.cs           Providers, OTLP export, options binding
+-- AgentRebooking.Tests/    Unit and telemetry tests, in-memory exporters
+-- spike/                   Task 2 spike and its captured spans
+-- config/
|   +-- otel-collector.yaml  oauth2client + otlp_http/b14 + debug
+-- scripts/
|   +-- test-api.sh          Two happy-path cases plus the six failure cases
|   +-- verify-scout.sh      Telemetry assertions against the collector log
+-- Dockerfile               Built from the example root, not from AgentRebooking/
+-- compose.yaml             app, postgres, otel-collector
+-- Makefile                 check, build-lint, test, ci, up, down, reset, test-api, verify-scout
+-- SPIKE-FINDINGS.md        What the Task 2 spike measured
+-- .env.example
```

## Resources

- [Microsoft Agent Framework handoff
  orchestration](https://learn.microsoft.com/en-us/agent-framework/workflows/orchestrations/handoff)
- [Microsoft Agent Framework tool
  approval](https://learn.microsoft.com/en-us/agent-framework/agents/tools/tool-approval)
- [Model Context Protocol C# SDK](https://github.com/modelcontextprotocol/csharp-sdk)
- [OpenTelemetry GenAI semantic conventions](https://github.com/open-telemetry/semantic-conventions-genai)
- [base14 Scout](https://base14.io)
- [base14 Scout documentation](https://docs.base14.io)
