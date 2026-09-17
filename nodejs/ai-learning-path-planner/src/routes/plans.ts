import type { LanguageModel } from "ai";
import { Hono } from "hono";
import { stream } from "hono/streaming";
import {
  buildLeadAgent,
  isTopicOutOfRange,
  type LeadOutcome,
  runLeadPlan,
} from "../agents/lead.js";
import type { Config } from "../config.ts";
import type { CorpusStore } from "../corpus/store.ts";
import { type PlanGap, SERVICE_GAP_REASONS } from "../plans/schema.js";
import type { PlanStore } from "../plans/store.ts";
import { takeRunCostUsd } from "../telemetry/enrich.js";
import {
  newRunCounters,
  type PlanOutcome,
  recordPlan,
  toolDefinitionTokens,
} from "../telemetry/metrics.js";

export interface PlansRouteDeps {
  store: CorpusStore;
  config: Config;
  plans: PlanStore;
  // Tests only. Undefined in production, so buildLeadAgent falls back to selectModel.
  model?: LanguageModel;
  researcherModels?: { small?: LanguageModel; large?: LanguageModel };
}

// c.req.json() can return null, a number, a string or an array. All of them fall through to
// undefined rather than throw, because 400 and 422 are told apart by what this returns.
function readTopic(body: unknown): string | undefined {
  if (typeof body !== "object" || body === null) return undefined;
  const topic = (body as { topic?: unknown }).topic;
  if (typeof topic !== "string") return undefined;
  const trimmed = topic.trim();
  return trimmed.length > 0 ? trimmed : undefined;
}

// NDJSON, one object per line: the first is written as soon as the request is accepted, the
// last carries the outcome, and there is no polling endpoint in between.
//
// The status is decided before the body streams, because headers are sent once.
// isTopicOutOfRange is the same pure predicate runLeadPlan uses for declined against planned,
// over the same immutable store, so the two always agree.
export function plansRoutes(deps: PlansRouteDeps): Hono {
  const plans = new Hono();

  plans.post("/plans", async (c) => {
    let body: unknown;
    try {
      body = await c.req.json();
    } catch {
      return c.json({ error: "request body must be valid JSON" }, 400);
    }

    const topic = readTopic(body);
    if (topic === undefined) {
      // 400, not 422: a missing or non-string topic never reaches the coverage check that
      // 422 reports on.
      return c.json({ error: "topic is required and must be a non-empty string" }, 400);
    }

    const declined = isTopicOutOfRange(deps.store, topic);

    // Minted outside the stream callback so the terminal error line carries it too: it is a
    // failed run's only route to its trace, through base14.plan.id.
    const id = deps.plans.create();
    const startedAt = performance.now();
    const counters = newRunCounters();

    // A new lead agent per request: it closes over the MAX_SUBTOPICS and MAX_ESCALATIONS
    // counters, which reset nowhere else. Built outside the stream callback so the failure
    // path, which has no outcome to read, still has the counters in scope.
    const agent = buildLeadAgent({
      store: deps.store,
      config: deps.config,
      model: deps.model,
      researcherModels: deps.researcherModels,
      run: { planId: id, counters },
    });

    const definitionTokens = {
      lead: toolDefinitionTokens(agent.tools, "lead", deps.config),
      researcher: toolDefinitionTokens(agent.tools, "researcher", deps.config),
    };

    // Here, not in runLeadPlan: this is where all three outcomes meet and the only place
    // holding the id, the clock and the config the tags come from. takeRunCostUsd also clears
    // the run's accumulator entry, on every path.
    const record = (status: PlanOutcome, gaps: PlanGap[]): void => {
      recordPlan({
        status,
        durationSeconds: (performance.now() - startedAt) / 1000,
        costUsd: takeRunCostUsd(id),
        counters,
        gaps,
        catalogue: deps.config.toolCatalogue,
        toolDefinitionTokens: definitionTokens,
      });
    };

    c.header("Content-Type", "application/x-ndjson; charset=utf-8");
    c.status(declined ? 422 : 200);

    return stream(
      c,
      async (s) => {
        await s.writeln(JSON.stringify({ event: "accepted", id, topic }));

        const outcome = await runLeadPlan(agent, { topic }, deps.store);
        deps.plans.complete(id, outcome);

        record(outcome.status, outcome.plan.gaps);

        await s.writeln(
          JSON.stringify({ event: "plan", id, status: outcome.status, plan: outcome.plan }),
        );
      },
      // The status is already on the wire, so this terminal line is the only signal left. A
      // run that throws after "accepted" otherwise ends the response like a successful one.
      async (err, s) => {
        // Without this an outage reads as an absence of traffic rather than failing traffic.
        // The gap is what separates an outage from a run that found nothing, and storing the
        // outcome keeps GET /plans/{id} answering for the id the client already holds.
        const outcome: LeadOutcome = {
          status: "failed",
          plan: {
            topic,
            weeks: [],
            gaps: [{ term: topic, reason: SERVICE_GAP_REASONS.service_error }],
          },
        };
        deps.plans.complete(id, outcome);
        record("failed", outcome.plan.gaps);
        await s.writeln(JSON.stringify({ event: "error", id, message: err.message }));
      },
    );
  });

  plans.get("/plans/:id", (c) => {
    const id = c.req.param("id");
    const outcome = deps.plans.get(id);
    if (outcome === undefined) {
      return c.json({ error: "plan not found" }, 404);
    }
    return c.json(outcome, 200);
  });

  return plans;
}
