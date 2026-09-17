# Rebooking agent spike findings

Recorded 2026-09-15 from `csharp/agent-rebooking/spike`, a throwaway console project on .NET 10.0.400.
Ten runs against local Ollama, five of them the fixed five-run set the plan asks for. Every name below was
observed at runtime, not read from documentation. Later tasks can script against these names without re-running
the spike.

A representative capture is committed under `spike/evidence/`: `spans-run1.jsonl` and `notes-run1.txt` for a
clean run, `notes-run8-no-rebook.txt` for the one run where the model skipped `rebook`, and
`spans-run7-content-capture.jsonl` for the run with content capture on. The per-token `WorkflowOutputEvent`
lines are stripped from the notes files; the wrapped lines that remain under an `AgentResponseEvent` are that
event's own text. Everything quoted below comes from those captures or from the runs listed in the timing
table.

## Notes for Task 3

`spike/Spike.csproj` must stay out of the solution and out of the Docker build context.

- It carries inline `PackageReference` versions. Central package management in the real project would break on
  them, and they are pinned for the spike, not for the app.
- A wildcard `dotnet sln add` or a `COPY . .` in the Dockerfile would pull it in.
- `csharp/agent-rebooking/.dockerignore` already excludes `spike/`. Keep that entry when you copy the house
  `.dockerignore` from `csharp/aspire-postgres`.
- Add projects to the `.sln` by name, not by wildcard.

## What the spike ran

- Two `ChatClientAgent` instances, `triage` (id and name `triage`) and `rebooking` (id and name `rebooking`),
  both built through `.AsBuilder().UseOpenTelemetry().Build()`.
- `AgentWorkflowBuilder.CreateHandoffBuilderWith(triage).WithHandoff(triage,
  rebooking).EmitAgentResponseEvents().Build()`.
- An in-process MCP server over two `System.IO.Pipelines.Pipe` instances, `WithStreamServerTransport` on the server
  and `StreamClientTransport` on the client, with tools `lookup_booking` and `rebook`.
- `rebook` wrapped on the client side in `ApprovalRequiredAIFunction`.
- A single app-owned root span `spike.run` from an `AgentRebooking` activity source, standing in for the
  `POST /runs` request span.
- Fixed prompt: "My booking is BK-1001 and my flight to Berlin was cancelled. Please rebook me on the cheapest
  alternative."

## Model decision

`qwen3.5:9b` stays. No change to the design's pin.

- Five of five runs in the fixed set handed off, called `lookup_booking`, paused on `rebook`, resumed and
  answered the traveller.
- All five picked `FL-201` at 180, the cheaper of the two alternatives.
- Across all ten runs the handoff succeeded ten times out of ten. The `rebook` call happened nine times out of
  ten: one run handed off, called `lookup_booking`, then read the alternatives back to the traveller and stopped.
  One miss in ten is not a rate, it is one miss. It is enough to say that `scripts/test-api.sh` needs a retry,
  because it asserts a `rebook` call in the tool log.
- Ollama accepts both `qwen3.5:9b` and `qwen3.5:9B`. `ollama list` prints the tag as `qwen3.5:9B`. Use the
  lowercase form in config and the README; the server matches either.

## Wall-clock timings

Measured from process start to the end of the workflow, CPU-only on the host.

| Run | Variant | Seconds | Approval reached at |
| --- | --- | --- | --- |
| 1 | baseline | 27.5 | 24.8s |
| 2 | baseline | 28.7 | 22.4s |
| 3 | baseline | 24.5 | 21.1s |
| 4 | baseline | 28.0 | 24.8s |
| 5 | baseline | 29.6 | 24.4s |
| 6 | minimal source set | 29.9 | 25.1s |
| 7 | content capture on | 27.0 | 21.5s |
| 8 | `TryGetDataAs` check | 19.1 | never, no `rebook` call |
| 9 | `TryGetDataAs` check | 24.8 | 18.8s |
| 10 | MCP source dropped | 30.3 | 27.8s |

Three LLM calls carry almost all of it: one triage turn, then two rebooking turns before the pause, then one more
after it. Each turn is 3 to 11 seconds. `RUN_TIMEOUT_SECONDS` at 300 is generous. The MCP round trips are 1 to 13
milliseconds.

## The handoff tool

The injected tool is named **`handoff_to_1`**, not `handoff_to_rebooking`.

- `HandoffWorkflowBuilderCore<T>.FunctionPrefix` is `handoff_to_`, and the suffix is a 1-based counter assigned
  as `HandoffAgentExecutor.CreateAgentHandoffContext` iterates the source agent's targets. The target agent's id
  is not used in the name.
- Targets are held in a `HashSet<HandoffTarget>`, so with two or more targets the number a given agent gets is
  not guaranteed to follow the order you added them in. With one target the name is fixed.
- The XML documentation on `FunctionPrefix` and the framework's own `DefaultHandoffInstructions` both say the name
  is `handoff_to_<agent_id>`. Both are wrong for 1.21.0.
- With triage holding exactly one handoff target the name was `handoff_to_1` in all ten runs.
- The tool is created as an `AIFunctionDeclaration`, a declaration with no body. It carries one argument,
  `reasonForHandoff`.
- It appears in `gen_ai.tool.definitions` on both the triage `chat` span and the triage `invoke_agent` span as
  `[{"type":"function","name":"handoff_to_1"}]`.
- It appears in the model's response as a `FunctionCallContent` with `Name == "handoff_to_1"`, visible on
  `AgentResponseEvent`.

There is **no `execute_tool handoff_to_1` span**. Because the handoff tool is a declaration, the function-invoking
chat client never runs it; `HandoffAgentExecutor` intercepts the call by name. Observed in ten of ten runs.
The handoff is visible in a trace only as the second `invoke_agent` span, and in `gen_ai.tool.definitions`.

## The approval pause and resume

Event flow, exactly as observed:

1. The workflow emits `Microsoft.Agents.AI.Workflows.RequestInfoEvent` from `WatchStreamAsync`.
2. `RequestInfoEvent.Request` is a `Microsoft.Agents.AI.Workflows.ExternalRequest`.
3. `Request.PortInfo.PortId` is `rebooking_rebooking_UserInput`, that is `{agentId}_{agentName}_UserInput`.
4. `Request.PortInfo.RequestType` is `Microsoft.Extensions.AI.ToolApprovalRequestContent` and
   `Request.PortInfo.ResponseType` is `Microsoft.Extensions.AI.ToolApprovalResponseContent`, both from
   `Microsoft.Extensions.AI.Abstractions` 10.10.0.
5. `Request.RequestId` looks like `29:rebooking_rebooking_UserInput:ficc_5b5accdf`. The last segment is
   `ficc_{toolCallId}`. Treat the whole string as opaque and carry it around; do not build it yourself.
6. `Request.Data` is a `PortableValue`. Its payload is a **bare `ToolApprovalRequestContent`**. There is no
   envelope: nothing implements `IExternalRequestEnvelope` on this path, so `GetInnerRequestContent` is not used.
   `PortableValue.Value` is internal. The public way in is
   `request.TryGetDataAs<ToolApprovalRequestContent>(out var content)`, verified to return `true` at runtime.
7. `ToolApprovalRequestContent.ToolCall` is declared as `Microsoft.Extensions.AI.ToolCallContent`, which carries
   only `CallId`. At runtime it is a `Microsoft.Extensions.AI.FunctionCallContent`, so cast it before reading the
   tool name or the arguments: `if (content.ToolCall is FunctionCallContent call)`. `call.Name` is the MCP tool
   name (`rebook`), `ToolCall.CallId` is the short id (for example `5b5accdf`), and `call.Arguments` is the
   parsed dictionary, for example `{"booking_ref":"BK-1001","flight_id":"FL-201"}`. Read the flight or hotel id
   from these arguments, do not parse the span.
8. `ToolApprovalRequestContent.RequestId` is `ficc_5b5accdf` and `RequiresConfirmation` is `true`.
9. Answer with `content.CreateResponse(approved: true)`, which returns a
   `Microsoft.Extensions.AI.ToolApprovalResponseContent`.
10. Wrap it with `externalRequest.CreateResponse(toolApprovalResponseContent)` to get an
    `Microsoft.Agents.AI.Workflows.ExternalResponse`.
11. Send it with `StreamingRun.SendResponseAsync(externalResponse)`.
12. Call `WatchStreamAsync` again. The first stream ends at the pause with
    `StreamingRun.GetStatusAsync()` reporting `RunStatus.Running`; the second one runs to `RunStatus.Idle`.

Other facts the run store will need:

- `InProcessExecution.RunStreamingAsync(workflow, List<ChatMessage>)` starts in `RunStatus.NotStarted` and does
  nothing until `run.TrySendMessageAsync(new TurnToken(emitEvents: true))` is sent. Without the turn token the
  workflow completes superstep 0 and stops. This is not in the design.
- `WatchStreamAsync(blockOnPendingRequest: false)` does return at the pause rather than parking, as the design
  assumed.
- A finished handoff workflow settles on `RunStatus.Idle`, not `RunStatus.Ended`. Treat `Idle` as terminal.
- Each call to `WatchStreamAsync` replays `WorkflowStartedEvent`, so do not treat that event as "new run".
- With `EmitAgentResponseEvents()` the workflow also emits streaming `WorkflowOutputEvent` per token. Filter them
  with `WorkflowOutputEventExtensions.IsIntermediate()`.
- The executor id is `{agentId}_{agentName}`, so `triage_triage` and `rebooking_rebooking`.

## Spans

Sixteen spans in one trace when the model completes the whole path, which is nine of the ten runs. The count
follows the work, so do not assert on it: the one run that skipped `rebook` produced twelve spans, and a run with
no listener on the MCP source produced ten. Assert on span names and parentage instead. Tree from run 1, captured
in `spike/evidence/spans-run1.jsonl`:

```text
spike.run                                    (app source, Server)
  invoke_agent triage(triage)                (Client)
    chat qwen3.5:9b                          (Client)
  invoke_agent rebooking(rebooking)          (Client)
    chat qwen3.5:9b                          (Client)
    chat qwen3.5:9b                          (Client)
    execute_tool lookup_booking              (Internal)
      tools/call lookup_booking              (Server)
  invoke_agent rebooking(rebooking)          (Client)   <- after the approval
    chat qwen3.5:9b                          (Client)
    execute_tool rebook                      (Internal)
      tools/call rebook                      (Server)
  server/discover                            (Client)
    server/discover                          (Server)
  tools/list                                 (Client)
    tools/list                               (Server)
```

- The agent span really is `invoke_agent {Name}({Id})`. With name and id both `triage` it reads
  `invoke_agent triage(triage)`. It carries `gen_ai.agent.id`, `gen_ai.agent.name`, `gen_ai.agent.description`.
- The chat span is `chat {model}`, here `chat qwen3.5:9b`.
- The tool span is `execute_tool {tool}`, here `execute_tool lookup_booking` and `execute_tool rebook`.
- MCP request spans are `{method}` or `{method} {tool}`: `server/discover`, `tools/list`,
  `tools/call lookup_booking`, `tools/call rebook`.
- Agent-level `UseOpenTelemetry()` alone produces the `invoke_agent`, `chat` and `execute_tool` spans, all three
  on the agent source. No separate `UseOpenTelemetry()` on the chat client is needed; `OpenTelemetryAgent`
  auto-wires an `OpenTelemetryChatClient` below the function-invoking chat client. The design is right here.
- The agent invoked after the approval produces a second `invoke_agent rebooking(rebooking)` span, a sibling of
  the first, not a child.
- Nothing appears from the `Microsoft.Agents.AI.Workflows` source. See the wrong claims below.

## Sources and meters to register

Three activity sources are enough. A run with only these produced the same sixteen spans as a run with six
sources registered.

| Source | Gives you |
| --- | --- |
| `Experimental.Microsoft.Agents.AI` | `invoke_agent`, `chat`, `execute_tool` |
| `Experimental.ModelContextProtocol` | `server/discover`, `tools/list`, `tools/call {tool}` |
| the example's own source, `AgentRebooking` | the root span and the approval spans |

`Microsoft.Agents.AI.Workflows` and `Experimental.Microsoft.Extensions.AI` contributed no spans. Registering them
is harmless but pointless in 1.21.0.

Meters observed, all of them emitting points:

| Meter | Instruments |
| --- | --- |
| `Experimental.Microsoft.Agents.AI` | `gen_ai.client.operation.duration`, `gen_ai.client.token.usage`, `gen_ai.client.operation.time_to_first_chunk`, `gen_ai.client.operation.time_per_output_chunk` |
| `Experimental.ModelContextProtocol` | `mcp.client.operation.duration`, `mcp.client.session.duration`, `mcp.server.operation.duration`, `mcp.server.session.duration` |

No `gen_ai.invoke_agent.*` instrument exists in 1.21.0. No `gen_ai.execute_tool.duration` either, so the MCP
client duration is not double counted, as the design says. The two chunk-timing instruments are extra and the
design does not mention them.

## MCP trace context over the in-process transport

Yes, `params._meta` carries `traceparent`, and yes, the server span's parent is the client-side span. Nothing in
the example has to do this.

An observed `_meta` from run 1, printed on the server inside `lookup_booking`:

```json
{
  "io.modelcontextprotocol/protocolVersion": "2026-07-28",
  "io.modelcontextprotocol/clientInfo": {"name": "Spike", "version": "1.0.0.0"},
  "io.modelcontextprotocol/clientCapabilities": {},
  "traceparent": "00-7019c0b8ac60c9ea8f26ecf0b55c8e17-456ad30fe6f2d933-01"
}
```

`456ad30fe6f2d933` is the span id of that run's `execute_tool lookup_booking` span, and the `tools/call
lookup_booking` server span's parent is that same id. `tracestate` is absent because nothing set one. The
transport reports `network.transport: pipe`.

## The MCP instrumentation needs a listener or it silently does nothing

`Diagnostics.ShouldInstrumentMessage` starts with `ActivitySource.HasListeners()` on
`Experimental.ModelContextProtocol`. If nothing is listening, the SDK skips the whole instrumentation branch.
Run 10 registered `Experimental.Microsoft.Agents.AI` and the app source but not the MCP one, and the result was:

- The `execute_tool lookup_booking` and `execute_tool rebook` spans still appeared, but with only the five
  `gen_ai.tool.*` attributes. Every `mcp.*` attribute was gone.
- `params._meta` lost `traceparent` entirely. The propagator is called with a null activity, so it writes
  nothing. Only `protocolVersion`, `clientInfo` and `clientCapabilities` were left.
- Ten spans instead of sixteen, and no error, no warning, no log line.

Task 7 has to register `Experimental.ModelContextProtocol` even though the example never asserts on an MCP client
span for `tools/call`, because the MCP attributes and the whole trace context hop depend on that listener.

## Content capture

With `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true` the framework adds span **attributes**, not events:

- `chat {model}` gets `gen_ai.system_instructions`, `gen_ai.input.messages`, `gen_ai.output.messages`, on all
  four chat spans.
- `invoke_agent {Name}({Id})` always gets `gen_ai.input.messages` and `gen_ai.output.messages`.
  `gen_ai.system_instructions` is there on the triage agent span but not on either rebooking agent span in
  `spike/evidence/spans-run7-content-capture.jsonl`. Do not write a README line that says agent spans never
  carry it; the honest statement is
  that it is present on some agent spans and not others, and the run that would separate cause from coincidence
  was not done.
- `execute_tool {tool}` gets nothing extra.

So the messages really do appear twice, on the agent span and on the chat span, as the design warns.

## Open, and deliberately not chased

- **Are `gen_ai.tool.name` and `gen_ai.operation.name` emitted twice on the merged `execute_tool` span?** The MCP
  SDK uses `AddTag` rather than `SetTag` when it enriches the outer tool activity, and the framework has already
  set both. `AddTag` appends, so duplicates are possible. The span recorder used here writes tags into a JSON
  object, which collapses duplicate keys, so the captures in `spike/evidence/` cannot answer this. Task 7's
  attribute assertions will settle it, and should be written to tolerate a duplicate rather than assume one
  value.
- **`handoff_to_N` with two or more targets.** Untested. This example has one handoff edge, so it does not block
  anything here. If a later example adds a second target, confirm the numbering before scripting against it.

## Design claims that turned out wrong

1. **"`execute_tool` for the handoff."** There is no handoff `execute_tool` span. The handoff tool is a
   declaration and the workflow intercepts the call. `verify-scout.sh` and the README must not look for one.
2. **"the workflow `message.send` spans."** The `Microsoft.Agents.AI.Workflows` source emits `workflow.build`,
   `workflow.session`, `workflow_invoke`, `executor.process {id}`, `edge_group.process` and `message.send`, but
   only when telemetry is enabled through `WorkflowBuilder.WithOpenTelemetry(...)`. The handoff builder has no
   such method, and `Workflow.TelemetryContext` and `WorkflowBuilder.SetTelemetryContext` are internal. In 1.21.0
   there is no public way to turn workflow spans on for a handoff workflow. Zero workflow spans in all ten runs.
3. **"both an execute_tool span and an MCP client span appear."** They do not, for `tools/call`. The C# SDK does
   detect an outer tool span: `Diagnostics.TryGetOuterToolExecutionActivity` checks whether
   `Activity.Current.OperationName` starts with `execute_tool` and, if so, reuses that activity instead of
   starting an MCP client span. The `execute_tool` span therefore carries the MCP attributes itself
   (`mcp.method.name`, `mcp.session.id`, `mcp.protocol.version`, `jsonrpc.request.id`, `network.transport`)
   alongside the `gen_ai.tool.*` ones, and the server span parents directly to it. `mcp.client.operation.duration`
   is still recorded. Requests without an outer tool span, such as `server/discover` and `tools/list`, do get
   their own client span, which is why those appear in pairs.
4. **The handoff tool name.** The design does not name it, but anything written from the framework docs would say
   `handoff_to_rebooking`. It is `handoff_to_1`.
5. **The run never starts without a turn token.** The design's run store description goes straight from
   `RunStreamingAsync` to `WatchStreamAsync`. A `TurnToken` has to be sent in between.

## Things to watch in the real app

- One trace per traveller message holds only while one ambient activity covers the whole run. In the spike the
  app-owned `spike.run` span was current for both the initial stream and the post-approval stream, and all sixteen
  spans landed in its trace. Without an ambient activity each `invoke_agent` starts its own trace: an early run
  with no root span produced four separate traces. In the real app the approval is answered in a different HTTP
  request, so unless the run store restores the run's trace context before resuming, the post-approval
  `invoke_agent` and `execute_tool` spans will land in the `POST /approvals/{id}` trace instead of the run trace.
  Task 3 has to decide that deliberately.
- `AllowMultipleToolCalls` is forced to `false` for every turn of any agent that has handoff targets, not just
  the turn on which it hands off. `HandoffAgentExecutor` builds one `ChatClientAgentRunOptions` in its
  constructor and passes it on every invocation. An agent with no targets, such as `rebooking` here, is
  unaffected and keeps whatever the app set.
- The spike wrapped the client-side `McpClientTool` in `ApprovalRequiredAIFunction`, which works.
  `ChatClientAgentOptions` also carries `DisableApprovalNotRequiredFunctionBypassing` and
  `DisableApprovalResponseBinding`; neither was needed.
- `ChatClientAgentOptions` has no `Instructions` property in 1.21.0. Instructions go on
  `ChatClientAgentOptions.ChatOptions.Instructions`.
