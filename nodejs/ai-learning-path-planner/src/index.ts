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

// One directory up, under both src and dist: tsc's outDir mirrors rootDir. Resolved from
// import.meta.url rather than process.cwd(), so the start directory does not matter.
const artifactPath = fileURLToPath(new URL("../data/corpus.json.gz", import.meta.url));
const artifact = await loadArtifact(artifactPath);

// Loaded once at boot and shared: the artifact and its store are immutable, unlike a lead
// agent, which is built per request.
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
