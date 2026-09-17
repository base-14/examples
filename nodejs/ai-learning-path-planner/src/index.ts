import { fileURLToPath } from "node:url";
import { serve } from "@hono/node-server";
import { Hono } from "hono";
import { loadConfig } from "./config.js";
import { CorpusStore, loadArtifact } from "./corpus/store.js";
import { PlanStore } from "./plans/store.js";
import { corpusRoutes } from "./routes/corpus.js";
import { health } from "./routes/health.js";
import { plansRoutes } from "./routes/plans.js";

const config = loadConfig();

// data/corpus.json.gz sits one directory above this file, both in src (tsx, development)
// and in dist (after `npm run build`): tsc's outDir mirrors rootDir exactly, so dist/index.js
// sits at the same depth below the package root as src/index.ts does. Resolving the path
// from import.meta.url, rather than from process.cwd(), is what makes that hold regardless
// of which directory the process was started from. src/llm/cost.ts resolves
// _shared/pricing.json the same way.
const artifactPath = fileURLToPath(new URL("../data/corpus.json.gz", import.meta.url));
const artifact = await loadArtifact(artifactPath);

// Loaded once at boot and shared across every request: the artifact and the CorpusStore
// built from it are immutable, unlike a lead agent, which is built fresh per request (see
// routes/plans.ts and agents/lead.ts).
const corpusStore = new CorpusStore(artifact);
const planStore = new PlanStore();

const app = new Hono();

app.route("/", health);
app.route("/", plansRoutes({ store: corpusStore, config, plans: planStore }));
app.route("/", corpusRoutes({ store: corpusStore }));

app.notFound((c) => c.json({ error: "not found" }, 404));
app.onError((err, c) => {
  console.error("Unhandled error", err);
  return c.json({ error: "internal server error" }, 500);
});

serve({ fetch: app.fetch, port: config.port }, (info) => {
  console.log(
    `ai-learning-path-planner listening on port ${info.port}, provider ${config.llmProvider}`,
  );
});
