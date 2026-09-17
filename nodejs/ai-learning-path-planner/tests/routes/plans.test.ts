import type { LanguageModelV4GenerateResult, LanguageModelV4Usage } from "@ai-sdk/provider";
import { MockLanguageModelV4 } from "ai/test";
import { Hono } from "hono";
import { describe, expect, it } from "vitest";
import type { Config } from "../../src/config.ts";
import type { CorpusArtifact } from "../../src/corpus/index-build.ts";
import { CorpusStore } from "../../src/corpus/store.ts";
import { SERVICE_GAP_REASONS } from "../../src/plans/schema.ts";
import { PlanStore } from "../../src/plans/store.ts";
import { type PlansRouteDeps, plansRoutes } from "../../src/routes/plans.ts";

function baseConfig(overrides: Partial<Config> = {}): Config {
  return {
    port: 3000,
    llmProvider: "ollama",
    ollamaBaseUrl: "http://host.docker.internal:11434/api",
    ollamaNumCtx: 32768,
    modelSmall: "gemma4:e2b",
    modelLarge: "qwen3.5:9B",
    priceModel: undefined,
    toolCatalogue: "deferred",
    maxSubtopics: 8,
    maxEscalations: 2,
    allowHostedProvider: false,
    captureMessageContent: false,
    ...overrides,
  };
}

const artifact: CorpusArtifact = {
  catalogue: [
    {
      path: "docs/guides/tracing.md",
      area: "docs",
      title: "Tracing basics",
      description: "Introduction to distributed tracing.",
      keywords: ["tracing"],
      headings: ["What is a trace"],
    },
  ],
  sections: [
    {
      path: "docs/guides/tracing.md",
      heading: "What is a trace",
      text: "A trace represents the end-to-end journey of a single request.",
    },
  ],
};

function store(): CorpusStore {
  return new CorpusStore(artifact);
}

function usage(input: number, output: number): LanguageModelV4Usage {
  return {
    inputTokens: { total: input, noCache: input, cacheRead: 0, cacheWrite: 0 },
    outputTokens: { total: output, text: output, reasoning: 0 },
  };
}

function stopWithObject(value: unknown): LanguageModelV4GenerateResult {
  return {
    content: [{ type: "text", text: JSON.stringify(value) }],
    finishReason: { unified: "stop", raw: "stop" },
    usage: usage(20, 20),
  };
}

function toolCallStep(
  toolName: string,
  input: unknown,
  callId: string,
): LanguageModelV4GenerateResult {
  return {
    content: [{ type: "tool-call", toolCallId: callId, toolName, input: JSON.stringify(input) }],
    finishReason: { unified: "tool-calls", raw: "tool_calls" },
    usage: usage(20, 5),
  };
}

function throwingModel(): MockLanguageModelV4 {
  return new MockLanguageModelV4({
    doGenerate: async () => {
      throw new Error("the model should not have been called");
    },
  });
}

function findingsModel(
  findings: { path: string; heading?: string; note: string }[],
): MockLanguageModelV4 {
  return new MockLanguageModelV4({
    doGenerate: stopWithObject({ subtopic: "x", findings }),
  });
}

// Reproduces the lead agent's own fan-out step shape from tests/agents/lead.test.ts:
// two research_subtopic tool calls, then a final structured-output step. Each instance
// keeps its own call counter, so it is only ever valid for driving one agent.generate()
// call end to end - exactly one HTTP request's worth of work.
function twoSubtopicLeadModel(): MockLanguageModelV4 {
  let callCount = 0;
  return new MockLanguageModelV4({
    doGenerate: async () => {
      callCount += 1;
      if (callCount <= 2) {
        return toolCallStep(
          "research_subtopic",
          { subtopic: ["a", "b"][callCount - 1] },
          `call-${callCount}`,
        );
      }
      return stopWithObject({ topic: "tracing", weeks: [], gaps: [] });
    },
  });
}

// The lead's loop is required to call a tool until it has researched something, and the
// SDK enforces that itself, so a mock lead that answers in prose before researching now
// fails the run rather than planning. Every lead model here researches first, the way a
// real run does. See prepareStep in agents/lead.ts.
const researchStep = () =>
  toolCallStep("research_subtopic", { subtopic: "tracing basics" }, "call-1");

function planningLeadModel(): MockLanguageModelV4 {
  let callCount = 0;
  return new MockLanguageModelV4({
    doGenerate: async () => {
      callCount += 1;
      return callCount === 1 ? researchStep() : stopWithObject(plannedPlan);
    },
  });
}

// A plan with a step in it. An empty plan is a failed run now, not a planned one, so a
// fixture that stands for a successful plan has to contain one. See agents/lead.ts.
const plannedPlan = {
  topic: "tracing",
  weeks: [
    {
      subtopic: "tracing basics",
      steps: [
        {
          title: "Read the trace intro",
          path: "docs/guides/tracing.md",
          kind: "doc",
          why: "Establishes the vocabulary.",
        },
      ],
    },
  ],
  gaps: [],
};

// One structured call per researcher run, whatever the loop did before it, so this counts
// researchers rather than model calls. See agents/researcher.ts.
function researcherRuns(model: MockLanguageModelV4): number {
  return model.doGenerateCalls.filter((call) => call.responseFormat?.type === "json").length;
}

function app(deps: PlansRouteDeps): Hono {
  return new Hono().route("/", plansRoutes(deps));
}

async function readNdjsonLines(res: Response): Promise<unknown[]> {
  const text = await res.text();
  return text
    .split("\n")
    .filter((line) => line.trim().length > 0)
    .map((line) => JSON.parse(line));
}

// Fails a hung read instead of letting it run into vitest's own timeout. If the response
// ever stops streaming, the first read never settles, and without this the regression shows
// up as a five-second timeout with no indication of the cause. 500ms is roughly a thousand
// times the work the handler does before it writes the accepted line, so it is not a race.
function withDeadline<T>(work: Promise<T>, ms: number, cause: string): Promise<T> {
  let timer: NodeJS.Timeout | undefined;
  const deadline = new Promise<never>((_, reject) => {
    timer = setTimeout(() => reject(new Error(cause)), ms);
  });
  return Promise.race([work, deadline]).finally(() => {
    if (timer !== undefined) clearTimeout(timer);
  }) as Promise<T>;
}

function postPlan(a: Hono, topic: unknown): Promise<Response> {
  return a.request("/plans", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ topic }),
  });
}

describe("POST /plans: decline path", () => {
  it("returns 422 and a declined outcome when the topic has no corpus coverage", async () => {
    const s = store();
    const deps: PlansRouteDeps = {
      store: s,
      config: baseConfig(),
      plans: new PlanStore(),
      model: throwingModel(),
    };

    const res = await postPlan(app(deps), "kubernetes");

    expect(res.status).toBe(422);
    const lines = await readNdjsonLines(res);
    expect(lines).toHaveLength(2);
    expect(lines[0]).toMatchObject({ event: "accepted", topic: "kubernetes" });
    expect(lines[1]).toMatchObject({ event: "plan", status: "declined" });
  });
});

describe("GET /plans/:id: declined outcome", () => {
  it("reports status declined, not planned, for the id a declined POST produced", async () => {
    const s = store();
    const planStore = new PlanStore();
    const deps: PlansRouteDeps = {
      store: s,
      config: baseConfig(),
      plans: planStore,
      model: throwingModel(),
    };
    const a = app(deps);

    const postRes = await postPlan(a, "kubernetes");
    expect(postRes.status).toBe(422);
    const lines = await readNdjsonLines(postRes);
    const id = (lines[1] as { id: string }).id;

    const getRes = await a.request(`/plans/${id}`);

    expect(getRes.status).toBe(200);
    const body = (await getRes.json()) as { status: string };
    expect(body.status).toBe("declined");
    expect(body.status).not.toBe("planned");
  });
});

describe("POST /plans: planned path", () => {
  it("returns 200, streams an accepted line then a planned line, and the plan is fetchable after", async () => {
    const s = store();
    const planStore = new PlanStore();
    const deps: PlansRouteDeps = {
      store: s,
      config: baseConfig(),
      plans: planStore,
      model: planningLeadModel(),
      researcherModels: {
        small: findingsModel([{ path: "docs/guides/tracing.md", note: "About tracing." }]),
      },
    };
    const a = app(deps);

    const res = await postPlan(a, "tracing");

    expect(res.status).toBe(200);
    expect(res.headers.get("content-type")).toContain("application/x-ndjson");
    const lines = await readNdjsonLines(res);
    expect(lines).toHaveLength(2);
    expect(lines[0]).toMatchObject({ event: "accepted", topic: "tracing" });
    expect(lines[1]).toMatchObject({
      event: "plan",
      status: "planned",
      plan: plannedPlan,
    });

    const id = (lines[1] as { id: string }).id;
    const getRes = await a.request(`/plans/${id}`);
    expect(getRes.status).toBe(200);
    expect(await getRes.json()).toEqual({
      status: "planned",
      plan: plannedPlan,
    });
  });
});

describe("POST /plans: malformed request", () => {
  it("returns 400, not 422, when topic is missing", async () => {
    const s = store();
    const deps: PlansRouteDeps = {
      store: s,
      config: baseConfig(),
      plans: new PlanStore(),
      model: throwingModel(),
    };
    const a = new Hono().route("/", plansRoutes(deps));

    const res = await a.request("/plans", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({}),
    });

    expect(res.status).toBe(400);
    expect(res.status).not.toBe(422);
  });

  it("returns 400 when topic is an empty string", async () => {
    const s = store();
    const deps: PlansRouteDeps = {
      store: s,
      config: baseConfig(),
      plans: new PlanStore(),
      model: throwingModel(),
    };

    const res = await postPlan(app(deps), "   ");

    expect(res.status).toBe(400);
  });

  it("returns 400 when the request body is not valid JSON", async () => {
    const s = store();
    const deps: PlansRouteDeps = {
      store: s,
      config: baseConfig(),
      plans: new PlanStore(),
      model: throwingModel(),
    };
    const a = new Hono().route("/", plansRoutes(deps));

    const res = await a.request("/plans", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: "not json",
    });

    expect(res.status).toBe(400);
  });

  it("returns 400, not 500, when the body is the literal JSON null", async () => {
    const s = store();
    const deps: PlansRouteDeps = {
      store: s,
      config: baseConfig(),
      plans: new PlanStore(),
      model: throwingModel(),
    };
    const a = new Hono().route("/", plansRoutes(deps));

    const res = await a.request("/plans", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: "null",
    });

    expect(res.status).toBe(400);
  });

  it("returns 400 when topic is a number, not a string", async () => {
    const s = store();
    const deps: PlansRouteDeps = {
      store: s,
      config: baseConfig(),
      plans: new PlanStore(),
      model: throwingModel(),
    };
    const a = new Hono().route("/", plansRoutes(deps));

    const res = await a.request("/plans", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ topic: 123 }),
    });

    expect(res.status).toBe(400);
  });
});

describe("GET /plans/:id: unknown id", () => {
  it("returns 404 for an id nothing was ever completed under", async () => {
    const s = store();
    const deps: PlansRouteDeps = {
      store: s,
      config: baseConfig(),
      plans: new PlanStore(),
    };

    const res = await app(deps).request("/plans/does-not-exist");

    expect(res.status).toBe(404);
  });
});

describe("PlansRouteDeps: fresh lead agent caps per request", () => {
  it("resets MAX_SUBTOPICS for a second request rather than carrying over an exhausted cap", async () => {
    const s = store();
    const small = findingsModel([{ path: "docs/guides/tracing.md", note: "About tracing." }]);
    const deps: PlansRouteDeps = {
      store: s,
      config: baseConfig({ maxSubtopics: 1 }),
      plans: new PlanStore(),
      model: twoSubtopicLeadModel(),
      researcherModels: { small },
    };
    const a = app(deps);

    const first = await postPlan(a, "tracing");
    expect(first.status).toBe(200);
    await first.text();
    expect(researcherRuns(small)).toBe(1);

    // A fresh model per request keeps the mock's own step-counting simple; what is under
    // test is whether the *cap* (MAX_SUBTOPICS, held in research_subtopic's closure,
    // rebuilt by buildLeadAgent) resets for this second request, not the model identity.
    deps.model = twoSubtopicLeadModel();
    const second = await postPlan(a, "tracing");
    expect(second.status).toBe(200);
    await second.text();

    // If the lead agent (and so the MAX_SUBTOPICS closure) were built once and reused
    // across requests, subtopicCalls would already be at 2 going into this request and
    // every further call would exceed maxSubtopics: 1, so small would see no new runs
    // here. A fresh agent per request researches exactly one more subtopic instead.
    expect(researcherRuns(small)).toBe(2);
  });
});

describe("POST /plans: failure before the stream opens", () => {
  it("answers 500 rather than a 200 carrying an error line", async () => {
    const deps: PlansRouteDeps = {
      store: store(),
      config: baseConfig({ llmProvider: "openai", allowHostedProvider: false }),
      plans: new PlanStore(),
    };
    const a = app(deps);

    // buildLeadAgent runs before stream() opens, so a throw from selectModel - here the
    // hosted-provider guard - happens with nothing yet on the wire. That is the one
    // failure in this route that can still answer with a real status code, and it should:
    // the terminal error line exists because a mid-stream failure has no other channel
    // left, not because 200 is the right answer to a request that never started.
    //
    // The 500 itself comes from Hono's default onError, not from this route: src/index.ts
    // installs the app-level handler that turns it into the JSON error body. What this
    // route is responsible for, and what is asserted here, is that no stream was opened
    // and no id was handed out for a run that never started.
    const res = await postPlan(a, "tracing");
    expect(res.status).toBe(500);
    expect(res.headers.get("content-type")).not.toContain("x-ndjson");
    expect(await res.text()).not.toContain("accepted");
  });
});

describe("POST /plans: mid-stream failure", () => {
  it("emits a terminal error line instead of a silently truncated 200", async () => {
    const s = store();
    const deps: PlansRouteDeps = {
      store: s,
      config: baseConfig(),
      plans: new PlanStore(),
      model: new MockLanguageModelV4({
        doGenerate: async () => {
          throw new Error("ollama unreachable");
        },
      }),
    };
    const a = app(deps);

    // The status is already 200 by the time the model throws: the topic has coverage, so
    // isTopicOutOfRange said "planned" before the stream opened. What is under test is
    // only the body - the terminal line has to say the run failed, since the status code
    // cannot change after the headers are sent.
    const res = await postPlan(a, "tracing");

    expect(res.status).toBe(200);
    const lines = await readNdjsonLines(res);
    expect(lines).toHaveLength(2);
    expect(lines[0]).toMatchObject({ event: "accepted", topic: "tracing" });
    expect(lines[1]).toMatchObject({ event: "error" });
    expect((lines[1] as { message: string }).message).toContain("ollama unreachable");
  });

  // failed covers both an outage and a run that found nothing, and the README says the
  // gap reason is what separates them. With an empty gap list an outage recorded no
  // reason at all, so there was nothing to read.
  it("records a gap that says the service failed, not an empty gap list", async () => {
    const plans = new PlanStore();
    const deps: PlansRouteDeps = {
      store: store(),
      config: baseConfig(),
      plans,
      model: new MockLanguageModelV4({
        doGenerate: async () => {
          throw new Error("ollama unreachable");
        },
      }),
    };

    const res = await postPlan(app(deps), "tracing");
    const lines = await readNdjsonLines(res);
    const id = (lines[0] as { id: string }).id;

    expect(plans.get(id)?.plan.gaps).toEqual([
      { term: "tracing", reason: SERVICE_GAP_REASONS.service_error },
    ]);
  });

  // The id is on the accepted line and again on the error line, so a client holding it
  // has every reason to expect GET to answer. It used to 404.
  it("stores the failed outcome, so GET answers for the id the client was handed", async () => {
    const plans = new PlanStore();
    const deps: PlansRouteDeps = {
      store: store(),
      config: baseConfig(),
      plans,
      model: new MockLanguageModelV4({
        doGenerate: async () => {
          throw new Error("ollama unreachable");
        },
      }),
    };
    const a = app(deps);

    const res = await postPlan(a, "tracing");
    const lines = await readNdjsonLines(res);
    const id = (lines[0] as { id: string }).id;

    const get = await a.request(`/plans/${id}`);

    expect(get.status).toBe(200);
    expect(await get.json()).toMatchObject({ status: "failed" });
  });
});

describe("POST /plans: the response actually streams", () => {
  it("delivers the accepted line to the client before the model call resolves", async () => {
    const s = store();
    let releaseModel: (() => void) | undefined;
    const gate = new Promise<void>((resolve) => {
      releaseModel = resolve;
    });
    const deps: PlansRouteDeps = {
      store: s,
      config: baseConfig(),
      plans: new PlanStore(),
      model: (() => {
        let callCount = 0;
        return new MockLanguageModelV4({
          doGenerate: async () => {
            callCount += 1;
            if (callCount === 1) {
              await gate;
              return researchStep();
            }
            return stopWithObject(plannedPlan);
          },
        });
      })(),
      researcherModels: {
        small: findingsModel([{ path: "docs/guides/tracing.md", note: "About tracing." }]),
      },
    };
    const a = app(deps);

    const res = await postPlan(a, "tracing");
    expect(res.body).not.toBeNull();
    const reader = res.body?.getReader();
    if (reader === undefined) throw new Error("response had no readable body");
    const decoder = new TextDecoder();

    const first = await withDeadline(
      reader.read(),
      500,
      "the accepted line did not arrive while the model call was still pending, so the response is buffering rather than streaming",
    );
    expect(first.done).toBe(false);
    const firstLine = JSON.parse(decoder.decode(first.value).trim().split("\n")[0] ?? "");
    expect(firstLine).toMatchObject({ event: "accepted", topic: "tracing" });

    // The gate is still shut here: this assertion ran, and passed, while runLeadPlan's
    // model call is still pending. A buffered (non-streaming) response could not have
    // delivered any bytes yet, since the handler that produces the rest of the body has
    // not returned.
    releaseModel?.();

    let restText = "";
    for (;;) {
      const next = await reader.read();
      if (next.done) break;
      restText += decoder.decode(next.value);
    }
    const finalLine = JSON.parse(restText.trim().split("\n").filter(Boolean).pop() ?? "");
    expect(finalLine).toMatchObject({ event: "plan", status: "planned" });
  });
});
