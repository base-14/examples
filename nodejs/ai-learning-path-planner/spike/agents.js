import { ToolLoopAgent, tool, isStepCount, Output } from 'ai';
import { createOllama } from 'ollama-ai-provider-v2';
import { z } from 'zod';

export const ollama = createOllama({ baseURL: 'http://localhost:11434/api' });

export const LEAD_MODEL = 'qwen3.5:9B';
export const SUB_MODEL = process.env.SPIKE_SUB_MODEL ?? 'gemma4:e2b';

const SECTIONS = {
  'docs/instrument/apps/auto-instrumentation/python.md': 'Python auto-instrumentation. Install opentelemetry-distro, run opentelemetry-instrument, set OTEL_EXPORTER_OTLP_ENDPOINT.',
  'docs/collect/collector-configuration.md': 'Collector configuration. Receivers, processors, exporters and the pipelines that join them.',
  'docs/visualize/scout-dashboards.md': 'Scout dashboards. Panels are SQL over the trace and metric tables.',
  'docs/instrument/apps/auto-instrumentation/django.md': 'Django tracing. The Django instrumentation wraps the WSGI handler and the ORM.',
};

const catalogue = [
  { path: 'docs/instrument/apps/auto-instrumentation/python.md', title: 'Python', area: 'instrument' },
  { path: 'docs/collect/collector-configuration.md', title: 'Collector configuration', area: 'collect' },
  { path: 'docs/visualize/scout-dashboards.md', title: 'Scout dashboards', area: 'visualize' },
  { path: 'docs/instrument/apps/auto-instrumentation/django.md', title: 'Django', area: 'instrument' },
];

const SubtopicFindings = z.object({
  subtopic: z.string(),
  summary: z.string(),
  citations: z.array(z.string()).min(1),
});

export function researcherTools() {
  return {
    search_docs: tool({
      description: 'Lexical search over the documentation corpus. Returns matching paths and titles.',
      inputSchema: z.object({ query: z.string().describe('search terms') }),
      execute: async ({ query }) => {
        const q = query.toLowerCase();
        return catalogue.filter((c) => c.title.toLowerCase().includes(q) || c.path.includes(q)).slice(0, 3);
      },
    }),
    outline: tool({
      description: 'Returns the heading outline of a document at a corpus path.',
      inputSchema: z.object({ path: z.string() }),
      execute: async ({ path }) => ({ path, headings: ['Overview', 'Setup', 'Verify'] }),
    }),
    fetch_section: tool({
      description: 'Fetches one section of a document by corpus path.',
      inputSchema: z.object({ path: z.string(), heading: z.string().optional() }),
      execute: async ({ path }) => ({ path, text: SECTIONS[path] ?? 'No such section.' }),
    }),
    list_examples: tool({
      description: 'Lists runnable examples for a language or framework.',
      inputSchema: z.object({ language: z.string() }),
      execute: async ({ language }) => [{ path: `${language}/hello-world`, title: `${language} hello world` }],
    }),
    fetch_example_file: tool({
      description: 'Fetches one file from a runnable example.',
      inputSchema: z.object({ path: z.string() }),
      execute: async ({ path }) => ({ path, text: '# example file' }),
    }),
  };
}

export function makeResearcher({ subtopic, full }) {
  const tools = researcherTools();
  return new ToolLoopAgent({
    id: `researcher-${subtopic}`,
    model: ollama(SUB_MODEL),
    instructions:
      'You research one subtopic against a documentation corpus. Call search_docs once, then fetch_section once on a path it returned. ' +
      'Then answer with the subtopic, a one sentence summary, and the corpus paths you read as citations. Be brief.',
    tools,
    activeTools: full ? undefined : ['search_docs', 'outline', 'fetch_section', 'list_examples', 'fetch_example_file'],
    stopWhen: isStepCount(4),
    output: Output.object({ schema: SubtopicFindings }),
    telemetry: { functionId: 'research-subtopic' },
  });
}

export function leadTools({ subtopics, full }) {
  const researcher = researcherTools();
  return {
    corpus_map: tool({
      description: 'Returns the areas of the corpus and how many documents each holds.',
      inputSchema: z.object({}),
      execute: async () => [
        { area: 'instrument', count: 2 },
        { area: 'collect', count: 1 },
        { area: 'visualize', count: 1 },
      ],
    }),
    check_coverage: tool({
      description: 'Checks whether a term appears in any document title, description, keyword or heading.',
      inputSchema: z.object({ term: z.string() }),
      execute: async ({ term }) => ({ term, covered: catalogue.some((c) => c.title.toLowerCase().includes(term.toLowerCase())) }),
    }),
    get_related: tool({
      description: 'Returns documents related to a corpus path by area.',
      inputSchema: z.object({ path: z.string() }),
      execute: async ({ path }) => catalogue.filter((c) => c.path !== path).slice(0, 2),
    }),
    research_subtopic: tool({
      description: 'Researches every subtopic of the request in parallel and returns their findings.',
      inputSchema: z.object({ note: z.string().optional() }),
      execute: async () => {
        const results = await Promise.all(
          subtopics.map(async (subtopic) => {
            const agent = makeResearcher({ subtopic, full });
            try {
              const result = await agent.stream({ prompt: `Subtopic: ${subtopic}` });
              const text = await result.text;
              const usage = await result.totalUsage;
              const steps = await result.steps;
              let structured = null;
              let structuredError = null;
              try {
                structured = await result.output;
              } catch (error) {
                structuredError = String(error?.message ?? error);
              }
              return {
                subtopic,
                text: text.slice(0, 400),
                structured,
                structuredError,
                totalUsage: usage,
                stepUsages: steps.map((s) => s.usage),
              };
            } catch (error) {
              return { subtopic, failed: String(error?.message ?? error) };
            }
          }),
        );
        globalThis.__spikeSubagentResults = results;
        return results.map((r) => ({
          subtopic: r.subtopic,
          summary: r.structured?.summary ?? r.text ?? r.failed,
          citations: r.structured?.citations ?? [],
        }));
      },
    }),
    ...(full ? researcher : {}),
  };
}

export function makeLead({ subtopics, full }) {
  const tools = leadTools({ subtopics, full });
  return new ToolLoopAgent({
    id: 'lead',
    model: ollama(LEAD_MODEL),
    instructions:
      'You build a study plan from a documentation corpus. Call research_subtopic exactly once to research all subtopics, ' +
      'then write a short ordered plan citing the paths the researchers returned. Do not call research_subtopic twice.',
    tools,
    activeTools: full ? undefined : ['corpus_map', 'check_coverage', 'get_related', 'research_subtopic'],
    stopWhen: isStepCount(4),
    telemetry: { functionId: 'lead-run' },
  });
}
