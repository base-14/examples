import { Hono } from "hono";
import { config } from "./config.ts";
import { logger } from "./logger.ts";
import { requestMetrics } from "./middleware/metrics.ts";
import { contracts } from "./routes/contracts.ts";
import { health } from "./routes/health.ts";
import { query } from "./routes/query.ts";
import { search } from "./routes/search.ts";

const app = new Hono();

app.use("*", requestMetrics);

app.route("/", health);
app.route("/api", contracts);
app.route("/api", query);
app.route("/api", search);

app.notFound((c) => c.json({ error: "not found" }, 404));
app.onError((err, c) => {
  logger.error("Unhandled error", { error: String(err) });
  return c.json({ error: "internal server error" }, 500);
});

console.log(`AI Contract Analyzer running on port ${config.port}`);

export default {
  port: config.port,
  fetch: app.fetch,
};
