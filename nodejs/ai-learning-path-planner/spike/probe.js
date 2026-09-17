// Falsification probes for step 2. Each prints whether inner agent spans nest or float.
import { NodeSDK } from '@opentelemetry/sdk-node';
import { resourceFromAttributes } from '@opentelemetry/resources';
import { trace, context, SpanKind } from '@opentelemetry/api';
import { registerTelemetry, ToolLoopAgent, tool, isStepCount } from 'ai';
import { OpenTelemetry } from '@ai-sdk/otel';
import { createOllama } from 'ollama-ai-provider-v2';
import { z } from 'zod';

const collected = [];
class P {
  onStart() {}
  onEnd(s) {
    collected.push({
      name: s.name, traceId: s.spanContext().traceId, spanId: s.spanContext().spanId,
      parentSpanId: s.parentSpanContext?.spanId ?? s.parentSpanId,
    });
  }
  shutdown() { return Promise.resolve(); }
  forceFlush() { return Promise.resolve(); }
}
const sdk = new NodeSDK({
  resource: resourceFromAttributes({ 'service.name': 'spike-probe' }),
  spanProcessors: [new P()],
});
sdk.start();

// No tracer passed: does the default tracer still nest correctly?
registerTelemetry(new OpenTelemetry());

const ollama = createOllama({ baseURL: 'http://localhost:11434/api' });
const tracer = trace.getTracer('spike-probe');

function inner(label) {
  return new ToolLoopAgent({
    id: `inner-${label}`,
    model: ollama('gemma4:e2b'),
    instructions: 'Answer in five words.',
    stopWhen: isStepCount(1),
    telemetry: { functionId: `inner-${label}` },
  });
}

async function runInner(label) {
  const r = await inner(label).stream({ prompt: 'Name one OpenTelemetry signal.' });
  await r.text;
}

function report(label, before) {
  const spans = collected.slice(before);
  const ids = new Set(spans.map((s) => s.spanId));
  const traces = new Set(spans.map((s) => s.traceId));
  const roots = spans.filter((s) => !s.parentSpanId || !ids.has(s.parentSpanId));
  console.log(JSON.stringify({
    probe: label,
    traceCount: traces.size,
    rootSpans: roots.map((s) => s.name),
    spanNames: spans.map((s) => s.name),
  }));
}

// Probe A: three concurrent inner agents inside a tool execution, no explicit tracer.
{
  const before = collected.length;
  const outerSpan = tracer.startSpan('probe.a.run', { kind: SpanKind.INTERNAL });
  await context.with(trace.setSpan(context.active(), outerSpan), async () => {
    const lead = new ToolLoopAgent({
      id: 'probe-a-lead',
      model: ollama('qwen3.5:9B'),
      instructions: 'Call fan_out exactly once, then reply with one sentence.',
      tools: {
        fan_out: tool({
          description: 'Researches three subtopics in parallel.',
          inputSchema: z.object({}),
          execute: async () => {
            await Promise.all(['a', 'b', 'c'].map((l) => runInner(l)));
            return 'done';
          },
        }),
      },
      stopWhen: isStepCount(2),
      telemetry: { functionId: 'probe-a-lead' },
    });
    const r = await lead.stream({ prompt: 'Research three subtopics.' });
    await r.text;
  });
  outerSpan.end();
  report('A: inside tool execution, default tracer', before);
}

// Probe B: the same three inner agents started with no ambient AI SDK context.
{
  const before = collected.length;
  await Promise.all(['a', 'b', 'c'].map((l) => runInner(l)));
  report('B: no ambient context (falsification)', before);
}

// Probe C: inner agents scheduled inside the tool but resolved after the tool span ended.
{
  const before = collected.length;
  const outerSpan = tracer.startSpan('probe.c.run', { kind: SpanKind.INTERNAL });
  let deferredWork = [];
  await context.with(trace.setSpan(context.active(), outerSpan), async () => {
    const lead = new ToolLoopAgent({
      id: 'probe-c-lead',
      model: ollama('qwen3.5:9B'),
      instructions: 'Call fan_out exactly once, then reply with one sentence.',
      tools: {
        fan_out: tool({
          description: 'Schedules three subtopic researchers.',
          inputSchema: z.object({}),
          execute: async () => {
            deferredWork = ['a', 'b', 'c'].map((l) => () => runInner(l));
            return 'scheduled';
          },
        }),
      },
      stopWhen: isStepCount(2),
      telemetry: { functionId: 'probe-c-lead' },
    });
    const r = await lead.stream({ prompt: 'Research three subtopics.' });
    await r.text;
  });
  outerSpan.end();
  await Promise.all(deferredWork.map((f) => f()));
  report('C: work deferred past the tool span', before);
}

await sdk.shutdown();
process.exit(0);
