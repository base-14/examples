import { collected, enrichSpanCalls, shutdown } from './telemetry.js';
import { trace, context, SpanKind } from '@opentelemetry/api';
import { createServer } from 'node:http';
import { makeLead, LEAD_MODEL, SUB_MODEL } from './agents.js';

const FULL = process.env.SPIKE_CATALOGUE === 'full';
const SUBTOPICS = ['collector-config', 'django-tracing', 'scout-dashboards'];
const tracer = trace.getTracer('learning-path-planner-spike');

const server = createServer(async (req, res) => {
  if (req.url !== '/plans') {
    res.writeHead(404).end();
    return;
  }
  const runSpan = tracer.startSpan('base14.plan.run', {
    kind: SpanKind.INTERNAL,
    attributes: { 'base14.agent.role': 'lead', 'base14.tool.catalogue': FULL ? 'full' : 'deferred' },
  });
  const runCtx = trace.setSpan(context.active(), runSpan);
  try {
    const out = await context.with(runCtx, async () => {
      const lead = makeLead({ subtopics: SUBTOPICS, full: FULL });
      const result = await lead.stream({
        prompt: 'Build a study plan for instrumenting a Django app and shipping its traces to Scout.',
      });
      const text = await result.text;
      const totalUsage = await result.totalUsage;
      const steps = await result.steps;
      return { text, totalUsage, stepUsages: steps.map((s) => s.usage) };
    });
    globalThis.__spikeLeadResult = out;
    res.writeHead(200, { 'content-type': 'application/json' }).end(JSON.stringify({ ok: true }));
  } catch (error) {
    globalThis.__spikeLeadError = String(error?.stack ?? error);
    res.writeHead(500).end(JSON.stringify({ error: String(error?.message ?? error) }));
  } finally {
    runSpan.end();
  }
});

function printTree() {
  const byParent = new Map();
  const byId = new Map();
  for (const s of collected) byId.set(s.spanId, s);
  for (const s of collected) {
    const key = s.parentSpanId && byId.has(s.parentSpanId) ? s.parentSpanId : `__root__${s.traceId}`;
    if (!byParent.has(key)) byParent.set(key, []);
    byParent.get(key).push(s);
  }
  const interesting = [
    'gen_ai.usage.input_tokens', 'gen_ai.usage.output_tokens',
    'gen_ai.operation.name', 'gen_ai.request.model', 'ai.telemetry.functionId',
    'base14.spike.span_type', 'base14.agent.role',
  ];
  const walk = (key, depth) => {
    const kids = (byParent.get(key) ?? []).sort((a, b) => a.startMs - b.startMs);
    for (const s of kids) {
      const attrs = interesting.filter((k) => s.attributes[k] !== undefined).map((k) => `${k}=${s.attributes[k]}`);
      console.log(`${'  '.repeat(depth)}- ${s.name}  [${(s.endMs - s.startMs).toFixed(0)}ms] ${attrs.join(' ')}`);
      walk(s.spanId, depth + 1);
    }
  };
  const roots = [...byParent.keys()].filter((k) => k.startsWith('__root__'));
  for (const r of roots) {
    console.log(`TRACE ${r.replace('__root__', '')}`);
    walk(r, 1);
  }
  const orphanParents = new Set();
  for (const s of collected) {
    if (s.parentSpanId && !byId.has(s.parentSpanId)) orphanParents.add(`${s.name} -> missing parent ${s.parentSpanId}`);
  }
  if (orphanParents.size) console.log('DANGLING PARENTS:', [...orphanParents]);
  console.log(`TRACE COUNT: ${new Set(collected.map((s) => s.traceId)).size}`);
}

server.listen(0, async () => {
  const port = server.address().port;
  const started = Date.now();
  const res = await fetch(`http://127.0.0.1:${port}/plans`, { method: 'POST' });
  const wall = Date.now() - started;
  await res.text();
  server.close();
  await new Promise((r) => setTimeout(r, 400));

  console.log(`\n=== RUN label=${process.env.SPIKE_LABEL ?? 'n/a'} catalogue=${FULL ? 'full' : 'deferred'} lead=${LEAD_MODEL} sub=${SUB_MODEL} wall=${wall}ms`);
  if (globalThis.__spikeLeadError) console.log('LEAD ERROR:', globalThis.__spikeLeadError);
  console.log('\n--- SPAN TREE ---');
  printTree();

  console.log('\n--- LEAD USAGE ---');
  console.log('totalUsage:', JSON.stringify(globalThis.__spikeLeadResult?.totalUsage));
  console.log('stepUsages:', JSON.stringify(globalThis.__spikeLeadResult?.stepUsages));

  console.log('\n--- SUBAGENT RESULTS ---');
  for (const r of globalThis.__spikeSubagentResults ?? []) {
    console.log(JSON.stringify({
      subtopic: r.subtopic,
      structuredOk: r.structured != null,
      structuredError: r.structuredError,
      failed: r.failed,
      totalUsage: r.totalUsage,
      stepUsages: r.stepUsages,
      structured: r.structured,
    }));
  }

  console.log('\n--- ENRICHSPAN CALLS ---');
  const byType = {};
  for (const c of enrichSpanCalls) byType[c.spanType] = (byType[c.spanType] ?? 0) + 1;
  console.log('counts by spanType:', JSON.stringify(byType));
  console.log('arg keys:', JSON.stringify([...new Set(enrichSpanCalls.flatMap((c) => c.argKeys))]));
  console.log('sample:', JSON.stringify(enrichSpanCalls.slice(0, 3)));

  console.log('\n--- SPAN TOKEN ATTRIBUTES ---');
  for (const s of collected) {
    const toks = Object.entries(s.attributes).filter(([k]) => k.includes('usage') || k.includes('token'));
    if (toks.length) console.log(s.name, JSON.stringify(Object.fromEntries(toks)));
  }

  console.log('\n--- ALL ATTRIBUTE KEYS SEEN ---');
  console.log(JSON.stringify([...new Set(collected.flatMap((s) => Object.keys(s.attributes)))].sort()));

  console.log(`\nWALL_MS=${wall}`);
  await shutdown();
  process.exit(0);
});
