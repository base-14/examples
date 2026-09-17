# AI SDK 7 telemetry spike - findings

Ran 2026-09-16 on Node 26.8.2, macOS arm64, against local Ollama at `http://localhost:11434`.
No hosted provider was called. The spike code is in `spike/` and is throwaway; it has its own
`package.json` and is not part of the example's build.

## What was run

- `spike/telemetry.js` starts the OTel Node SDK, registers `OpenTelemetry` from `@ai-sdk/otel`
  through `registerTelemetry`, and installs a span processor that keeps every finished span in
  memory alongside the console exporter.
- `spike/agents.js` builds a lead `ToolLoopAgent` on `qwen3.5:9B` whose `research_subtopic`
  tool runs three `ToolLoopAgent` calls on `gemma4:e2b` concurrently through `Promise.all`,
  and a nine-tool catalogue matching the design's split.
- `spike/run.js` serves `POST /plans` on `node:http`, opens a `base14.plan.run` span, runs the
  lead inside it, then prints the span tree, usage, `enrichSpan` calls and every attribute key
  seen. Logs are in `spike/out/run-1.log` through `spike/out/run-5.log`.
- `spike/probe.js` holds three parentage probes, including one written to fail.
  Log: `spike/out/probe.log`.
- `spike/tooldefs.js` measures the `activeTools` effect. Log: `spike/out/tooldefs.log`.
- `spike/attrprobe.js` checks `runtimeContext` in `enrichSpan` and cost written at span end.
  Log: `spike/out/attrprobe.log`.
- `spike/instrument.mjs` is the ESM entry that registers the instrumentation hook.

Versions installed: `ai` 7.0.102, `@ai-sdk/otel` 1.0.102, `ollama-ai-provider-v2` 4.0.1,
`@opentelemetry/sdk-node` 0.222.0, `@opentelemetry/instrumentation-http` 0.222.0,
`@opentelemetry/api` 1.9.0, `zod` 4.6.5.

## 1. Span parentage across concurrent subagents

The three concurrent subagent spans parent to the lead's tool span. The shape held identically
in all five runs and in the smoke run before them.

```text
POST                                    HTTP server span
`-- base14.plan.run                     opened by hand in the route
    `-- invoke_agent qwen3.5:9B         lead operation span
        |-- step 1
        |   |-- chat qwen3.5:9B
        |   `-- execute_tool research_subtopic
        |       |-- invoke_agent gemma4:e2b -- step 1 -- chat gemma4:e2b
        |       |-- invoke_agent gemma4:e2b -- step 1 -- chat gemma4:e2b
        |       `-- invoke_agent gemma4:e2b -- step 1 -- chat gemma4:e2b
        `-- step 2
            `-- chat qwen3.5:9B
```

One trace per request in all five runs, no dangling parents, no floating spans.

Nothing extra had to be done to make this work. No `context.with` around the subagent calls, no
wrapping of the tool execution and no tracer of our own. The mechanism is in
`node_modules/@ai-sdk/otel/dist/index.js`.

- `onToolExecutionStart` at line 1279 starts the tool span against an explicit parent context,
  the step context, rather than against whatever is ambient.
- `executeTool` at line 688 runs the tool's `execute` inside `context.with` of that tool span's
  context, so the tool body sees the tool span as the active span.
- `onGenerateStart` at line 1044 starts an operation span against `context.active()`, which
  inside a tool body is the tool span.

Concurrency is safe because each tool call gets its own context object and `context.with`
resolves through `AsyncLocalStorage`, which forks per call rather than being a single mutable
current-span slot.

### Probes, including one written to fail

Results are in `spike/out/probe.log`.

- Probe A runs the same fan-out with no `tracer` passed to the `OpenTelemetry` integration. One
  trace, root `probe.a.run`, all inner spans nested. The `tracer` option is not what makes
  parentage work; it only chooses which tracer emits the spans.
- Probe B runs the three subagents with no ambient AI SDK context. Three separate traces, three
  root `invoke_agent gemma4:e2b` spans. This is the falsification: the check can go red.
- Probe C schedules the three subagents inside the tool body as closures and invokes them after
  the tool has returned and its span has ended. Four traces: `probe.c.run` plus three floating
  roots. The context is captured when the async work starts, not when the closure is created.

Probe C is the trap for later tasks. Subagent work has to start while the tool's `execute`
promise is still being awaited. Anything deferred past the tool's return loses the parent.

### What this costs the design

Two span levels sit between `base14.plan.run` and the model and tool spans that the design's
diagram puts directly under it: `invoke_agent <model>` and `step <n>`. The diagram in the
telemetry section of the design has been corrected.

The HTTP server span is named `POST`, not `POST /plans`, because the http instrumentation has
no route to work from. If the README or a verification assertion wants the path, it has to come
from `url.path`, which is present.

## 2. Token counts and where they can be read

Both sources work and they agree.

- `result.totalUsage` is the run total, summed across steps. For the lead in
  `spike/out/smoke.log` it read 1173 input and 140 output tokens.
- `result.steps[i].usage` is per step, and in the tool loop a step is one model call. The lead's
  two steps read 507 and 666 input tokens, which matches its two `chat` spans exactly.
- Each subagent's own `result.totalUsage` is that subagent's total, because each subagent is its
  own run. The three read 326, 326 and 327 input tokens.

On spans, `gen_ai.usage.input_tokens` and `gen_ai.usage.output_tokens` are set on two span types
and no others.

| Span | Carries token counts |
| --- | --- |
| `chat <model>` | Yes, for that one model call. |
| `invoke_agent <model>` | Yes, the total for that agent run. |
| `step <n>` | No. |
| `execute_tool <name>` | No. |

Per-subagent cost attribution can therefore read either the subagent's `invoke_agent` span or
its `totalUsage`. Per-model-call cost has to come from the `chat` span or from `steps[i].usage`.

## 3. `enrichSpan`

It receives exactly four fields: `spanType`, `operationId`, `callId` and `runtimeContext`.
`spanType` is one of `operation`, `step`, `languageModel`, `tool`, `embedding` and `reranking`.
In one run it fired four times for `operation`, five for `step`, five for `languageModel` and
once for `tool`, which is once per span it creates.

Two limits follow from that argument list.

- It fires when a span is created, so token counts are not available to it. `base14.gen_ai.cost`
  cannot be produced from `enrichSpan`. The design's attribute table said it could and has been
  corrected.
- It carries no tool name and no tool input, so a per-tool-call attribute such as
  `base14.subtopic` cannot be derived from the tool call itself.

`runtimeContext` reaches it on every span type, but only when `telemetry.includeRuntimeContext`
names each key. **Corrected in Task 8.** This section originally read as though the values passed
to the agent constructor arrived unaided. They do not: without `includeRuntimeContext`,
`enrichSpan` still fires for `operation`, `step` and `languageModel`, and `runtimeContext` is `{}`
every time. The boolean form, `includeRuntimeContext: true`, also yields `{}`. It has to be a
per-key map.

The measurement here was never wrong, only its write-up. `spike/attrprobe.js:56` passes
`includeRuntimeContext: { subtopic: true, planId: true }`, so the probe contained the thing that
made it work and the finding attributed the result to the agent constructor instead. Task 8
re-probed `@ai-sdk/otel` 1.0.102 and its reviewer reproduced the same result independently.

This matters more than a documentation slip. Omitting `includeRuntimeContext` does not fail: the
spans are created, the run succeeds, the tests pass, and every `base14.*` attribute is simply
absent. Nothing reports it.

With the keys named, a researcher agent constructed per subtopic can set `base14.subtopic` and
`base14.agent.role` from `runtimeContext` on every span of that agent's run. That is the route the
design takes.

For cost, a span processor ordered ahead of the exporting processor can read
`gen_ai.usage.input_tokens` and `gen_ai.usage.output_tokens` in its `onEnd` and write
`base14.gen_ai.cost` and `base14.gen_ai.cost.simulated` into the span's attributes. A downstream
collecting processor saw both values. `spike/attrprobe.js` does this, logged in
`spike/out/attrprobe.log`.

This route relies on span processors sharing the same span object and running in registration
order, both of which are implementation details of the SDK rather than a documented contract.
If that assumption stops holding, the fallback is to put cost on the spans the example creates
itself, `base14.plan.run` and `base14.plan.subtopic`, where the value can be set before `end()`
instead of read back from another processor.

Two attribute notes.

- `telemetry.functionId` is emitted as `gen_ai.agent.name`, on the `operation` span only. The
  legacy integration's `ai.telemetry.functionId` is not emitted by `OpenTelemetry`.
- `telemetry.includeRuntimeContext` emits `ai.settings.context.<key>` on the `operation` and
  `step` spans, not on the `languageModel` span.

## 4. `activeTools`

It does change what is sent to the provider. `spike/tooldefs.js` ran the same prompt twice
against the same nine-tool catalogue on `qwen3.5:9B`, stopping after one step.

| Catalogue | Tool definitions | Definition JSON | Input tokens |
| --- | --- | --- | --- |
| Deferred, four tools | 4 | 1151 chars | 474 |
| Full, nine tools | 9 | 2661 chars | 790 |

The difference is 316 input tokens per step. The `gen_ai.tool.definitions` span attribute lists
only the active tools, which gives the verification script a second way to assert the same
thing without reading token counts.

## 5. Five runs

Same request each time, deferred catalogue, three subtopics.

| Run | Wall clock | Structured outputs valid | Traces |
| --- | --- | --- | --- |
| 1 | 21.75 s | 3 of 3 | 1 |
| 2 | 23.41 s | 3 of 3 | 1 |
| 3 | 24.56 s | 3 of 3 | 1 |
| 4 | 25.07 s | 3 of 3 | 1 |
| 5 | 25.60 s | 3 of 3 | 1 |

Median 24.56 s, mean 24.08 s, spread 3.85 s.

**Corrected in Task 9.** These five runs are a real measurement of the spike harness, and they are
not a measurement of the finished service. The spike gave its subagents no tools, so
`Output.object` was safe there; in the service the lead and the researchers both carry tools, and a
response format alongside tools suppresses tool calls outright (see the correction in section 3 and
the note below). The service therefore drops the response format from both tool loops and shapes
its output in a separate call afterwards, which is more model calls and far more wall clock.

Measured on the finished service over fifteen consecutive runs against local Ollama: a planned run
takes 72 s to 167 s with a fan-out of two to four subtopics, and a declined run takes about 0.02 s.
The README publishes that band, not the one above. Anyone reaching for the spike's numbers should
take them as evidence about the spike.

`gemma4:e2b` returned schema-valid structured output on all fifteen subagent calls, using
`Output.object` with a zod schema of three fields, one of them an array with a minimum length.
No larger model was needed, so `qwen3.5:9B` stays the escalation tier rather than the researcher
tier.

This result is what made the `Output.object` problem invisible until Task 9. These subagent calls
had no tools, so nothing here could have exposed the interaction. What the service hit is narrower
than "structured output does not work": `ollama-ai-provider-v2` sends `think: false` on every
request unless told otherwise, and `think: false` combined with a response format suppresses tool
calls. Either one alone is harmless, which is why toggling the format looked like the whole
explanation and was not.

The advice in this paragraph held up exactly. The models are slow enough that the fan-out is the
wall clock. The three subagent calls on one
Ollama instance serialise on the GPU: their spans overlap but their durations stack, 6.6 s, 7.7 s
and 8.7 s inside an 8.7 s tool span. Any later claim about parallel speedup has to account for
that, and the README's numbers should come from a measured run rather than from the fan-out
count.

## 6. API surprises

- Under ESM on Node 26, the HTTP server span is missing unless the instrumentation hook is
  registered before anything imports `node:http`. The first run of `spike/run.js` produced a
  correct agent tree with no HTTP span at all. Running it as `node --import ./instrument.mjs
  run.js`, where `spike/instrument.mjs` calls `module.register` with
  `@opentelemetry/instrumentation/hook.mjs`, fixed it. Task 8 has to set this up in the
  service's start command.
- Node 26 emits `DEP0205` for `module.register`, pointing at `module.registerHooks`. The
  otel hook is written for `module.register`, so the warning stands for now. It is a warning;
  the hook works.
- `ToolLoopAgent.stream` returns a promise. It has to be awaited before the result's fields are
  reachable, unlike `streamText`.
- The `ollama-ai-provider-v2` default base URL already ends in `/api`, so `OLLAMA_BASE_URL`
  should carry the `/api` suffix or be left unset.
- `@ai-sdk/otel` exports `OpenTelemetry` and `LegacyOpenTelemetry`. They emit different
  attribute names for the same things. Everything here is measured against `OpenTelemetry`.

## Pins to add

The spike needed three packages the design's pin table does not list, all pulled in by the
telemetry setup rather than chosen: `@opentelemetry/sdk-trace-base` 2.2.0,
`@opentelemetry/resources` 2.2.0 and `@opentelemetry/semantic-conventions` 1.39.0. The design's
table has been extended.

The spike used `@opentelemetry/instrumentation-http` 0.222.0 directly rather than
`@opentelemetry/auto-instrumentations-node` 0.80.0, which the design pins. The ESM hook finding
applies either way, but the auto-instrumentations bundle has not been exercised here.

`spike/package-lock.json` resolves `@opentelemetry/api` twice: 1.9.0 at the top level and 1.9.1
nested under `@ai-sdk/otel`. Nothing broke in the measured runs, but duplicate API instances are
a known source of context-propagation bugs in OpenTelemetry JS. Task 8 should check that the
real service resolves a single `@opentelemetry/api` version before relying on this spike's
parentage and context findings.
