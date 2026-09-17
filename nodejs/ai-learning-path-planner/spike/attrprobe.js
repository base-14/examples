// Does runtimeContext reach enrichSpan, and can a span processor add cost at onEnd?
import { NodeSDK } from '@opentelemetry/sdk-node';
import { resourceFromAttributes } from '@opentelemetry/resources';
import { trace } from '@opentelemetry/api';
import { registerTelemetry, ToolLoopAgent, isStepCount } from 'ai';
import { OpenTelemetry } from '@ai-sdk/otel';
import { createOllama } from 'ollama-ai-provider-v2';

const seen = [];
const RATE_IN = 0.15 / 1e6, RATE_OUT = 0.60 / 1e6;

class CostProcessor {
  onStart() {}
  onEnd(span) {
    const i = span.attributes['gen_ai.usage.input_tokens'];
    const o = span.attributes['gen_ai.usage.output_tokens'];
    if (typeof i === 'number' && typeof o === 'number') {
      span.attributes['base14.gen_ai.cost'] = i * RATE_IN + o * RATE_OUT;
      span.attributes['base14.gen_ai.cost.simulated'] = true;
    }
  }
  shutdown() { return Promise.resolve(); }
  forceFlush() { return Promise.resolve(); }
}
class Collector {
  onStart() {}
  onEnd(span) { seen.push({ name: span.name, attributes: { ...span.attributes } }); }
  shutdown() { return Promise.resolve(); }
  forceFlush() { return Promise.resolve(); }
}

const sdk = new NodeSDK({
  resource: resourceFromAttributes({ 'service.name': 'spike-attrprobe' }),
  spanProcessors: [new CostProcessor(), new Collector()],
});
sdk.start();

const enrich = [];
registerTelemetry(new OpenTelemetry({
  tracer: trace.getTracer('spike-attrprobe'),
  runtimeContext: true,
  enrichSpan: (o) => {
    enrich.push({ spanType: o.spanType, runtimeContext: o.runtimeContext });
    const subtopic = o.runtimeContext?.subtopic;
    return subtopic ? { 'base14.subtopic': String(subtopic), 'base14.agent.role': 'researcher' } : undefined;
  },
}));

const ollama = createOllama({ baseURL: 'http://localhost:11434/api' });
const agent = new ToolLoopAgent({
  id: 'attrprobe-researcher',
  model: ollama('gemma4:e2b'),
  instructions: 'Answer in five words.',
  stopWhen: isStepCount(1),
  runtimeContext: { subtopic: 'django-tracing', planId: 'plan-123' },
  telemetry: { functionId: 'research-subtopic', includeRuntimeContext: { subtopic: true, planId: true } },
});
const r = await agent.stream({ prompt: 'Name one OpenTelemetry signal.' });
await r.text;

console.log('enrichSpan runtimeContext per spanType:', JSON.stringify(enrich));
for (const s of seen) {
  const keys = Object.entries(s.attributes).filter(([k]) => /base14|agent.name|usage|settings.context/.test(k));
  console.log(s.name, JSON.stringify(Object.fromEntries(keys)));
}
await sdk.shutdown();
process.exit(0);
