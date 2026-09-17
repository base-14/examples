import { collected, shutdown } from './telemetry.js';
import { ToolLoopAgent, isStepCount } from 'ai';
import { ollama, leadTools, LEAD_MODEL } from './agents.js';

const PROMPT = 'Build a study plan for instrumenting a Django app and shipping its traces to Scout.';
const SUBTOPICS = ['collector-config', 'django-tracing', 'scout-dashboards'];

async function measure(label, activeTools) {
  const before = collected.length;
  const agent = new ToolLoopAgent({
    id: `tooldefs-${label}`,
    model: ollama(LEAD_MODEL),
    instructions: 'You build a study plan from a documentation corpus.',
    tools: leadTools({ subtopics: SUBTOPICS, full: true }),
    activeTools,
    stopWhen: isStepCount(1),
    telemetry: { functionId: `tooldefs-${label}` },
  });
  const result = await agent.stream({ prompt: PROMPT });
  await result.text;
  const usage = await result.totalUsage;
  const chat = collected.slice(before).find((s) => s.name.startsWith('chat '));
  let defs = chat?.attributes['gen_ai.tool.definitions'];
  if (typeof defs === 'string') defs = JSON.parse(defs);
  const names = (defs ?? []).map((d) => d.name ?? d.function?.name ?? d.type);
  console.log(JSON.stringify({
    label,
    toolDefinitionCount: names.length,
    toolNames: names,
    toolDefinitionChars: JSON.stringify(defs ?? []).length,
    spanInputTokens: chat?.attributes['gen_ai.usage.input_tokens'],
    resultInputTokens: usage.inputTokens,
  }));
  return usage.inputTokens;
}

const deferred = await measure('deferred', ['corpus_map', 'check_coverage', 'get_related', 'research_subtopic']);
const full = await measure('full', undefined);
console.log(`INPUT_TOKEN_DELTA full-deferred = ${full - deferred}`);
await shutdown();
process.exit(0);
