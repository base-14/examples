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
  // Only ever set by a test. Production leaves these undefined so buildLeadAgent falls
  // back to selectModel(tier, config), which is what wires up the real Ollama provider.
  model?: LanguageModel;
  researcherModels?: { small?: LanguageModel; large?: LanguageModel };
}

// body is whatever c.req.json() parsed, which can be anything valid JSON allows -
// including null, a number, a string or an array. Every one of those has to fall through
// to undefined here rather than throw, since the only thing that separates "malformed
// request" (400) from "well-formed but out of corpus range" (422) is that this function
// returns cleanly either way.
function readTopic(body: unknown): string | undefined {
  if (typeof body !== "object" || body === null) return undefined;
  const topic = (body as { topic?: unknown }).topic;
  if (typeof topic !== "string") return undefined;
  const trimmed = topic.trim();
  return trimmed.length > 0 ? trimmed : undefined;
}

// POST /plans streams newline-delimited JSON (NDJSON, one JSON object per line) rather
// than plain JSON, because the design calls for one request that streams progress and
// ends with the plan. There is no polling endpoint and no separate approval step, so this
// is the only signal a caller gets before the plan is final. The first line is written as
// soon as the request is accepted, before the (possibly slow) lead agent run starts; the
// last line carries the outcome. A shell script can assert against this with `tail -n 1`
// and `jq`, which is what scripts/test-api.sh (Task 9) does.
//
// The HTTP status is decided before the body starts streaming, since headers can only be
// sent once: isTopicOutOfRange(topic) is checked here, synchronously, using the exact same
// predicate runLeadPlan calls internally to decide "declined" vs "planned" (see
// agents/lead.ts). Both calls run against the same immutable store and the same topic, so
// they always agree - this is not a race, just the same pure check made twice.
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
      // 400, not 422: 422 means "the topic is out of corpus range", a decision the lead
      // agent's coverage check makes. A missing, non-string or empty topic never reaches
      // that check - it is a malformed request, which is a different kind of problem and
      // gets a different status so a caller (and Task 9's script) never has to guess which
      // one a given 4xx means.
      return c.json({ error: "topic is required and must be a non-empty string" }, 400);
    }

    const declined = isTopicOutOfRange(deps.store, topic);

    // Minted here rather than inside the stream callback so the terminal error line can
    // carry it too. A client that only ever sees {"event":"error"} otherwise has no way
    // to find the run's trace by base14.plan.id, which every AI SDK span in the run
    // carries. Nothing is reserved that was not already being reserved: every
    // request that reaches this line opens a stream and takes an id, declined ones
    // included, and the malformed-request cases returned 400 further up.
    const id = deps.plans.create();
    const startedAt = performance.now();
    const counters = newRunCounters();

    // A new lead agent for every request: buildLeadAgent closes over the MAX_SUBTOPICS and
    // MAX_ESCALATIONS counters (see agents/lead.ts), and those only reset when
    // buildLeadAgent runs. Built here rather than inside the stream callback so the run's
    // counters and tool definitions are in scope for the failure path too, which is the
    // one path that has no outcome to read them from.
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

    // Recorded here, not inside runLeadPlan: this is the only place that holds the plan
    // id, the clock that started when the request was accepted and the config the tags
    // come from, and it is where all three outcomes - declined, planned and failed - come
    // back together. runLeadPlan stays a function that plans, with a signature the agent
    // tests can call without a meter in scope. takeRunCostUsd also clears the run's entry
    // in the cost accumulator, on every path including the failing one.
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
      // The HTTP status (200 or 422) is already on the wire by the time this runs - there
      // is no way to turn a mid-stream failure into a different status code. This
      // terminal NDJSON line is the only signal a client has left: without it, a run that
      // throws after "accepted" (an Ollama outage, for example) ends the response exactly
      // the way a run that never got that far would, and a caller reading only the status
      // code, or only checking that a body arrived, reads it as success.
      async (err, s) => {
        // A run that fails mid-stream is the case metrics exist for. Without this it is
        // the one outcome that records nothing at all, so an outage reads as an absence of
        // traffic rather than as failing traffic. The fan-out is whatever was reached
        // before the failure and the duration is measured to the point of failure.
        //
        // It carries a gap, and it is stored. failed covers both an outage and a run that
        // found nothing, and the README says the gap reason is what separates them: with
        // an empty gap list an outage recorded no reason at all, so there was nothing to
        // read. Storing the outcome is what keeps GET /plans/{id} answering for an id the
        // client was already handed on the accepted line and again on the error line.
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
