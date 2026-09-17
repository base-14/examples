import { describe, expect, it } from "vitest";
import type { LeadOutcome } from "../../src/agents/lead.ts";
import { MAX_STORED_PLANS, PlanStore } from "../../src/plans/store.ts";

function outcome(topic: string, status: LeadOutcome["status"] = "planned"): LeadOutcome {
  return { status, plan: { topic, weeks: [], gaps: [] } };
}

describe("PlanStore", () => {
  it("returns undefined for an id nothing was ever completed under", () => {
    const store = new PlanStore();

    expect(store.get("does-not-exist")).toBeUndefined();
  });

  it("returns undefined for a created id before complete() runs", () => {
    const store = new PlanStore();
    const id = store.create();

    expect(store.get(id)).toBeUndefined();
  });

  it("returns the outcome complete() stored, keyed by the id create() returned", () => {
    const store = new PlanStore();
    const id = store.create();

    store.complete(id, outcome("tracing"));

    expect(store.get(id)).toEqual(outcome("tracing"));
  });

  it("gives every call to create() a distinct id", () => {
    const store = new PlanStore();

    const first = store.create();
    const second = store.create();

    expect(first).not.toBe(second);
  });

  it("keeps two completed outcomes independently addressable", () => {
    const store = new PlanStore();
    const tracing = store.create();
    const metrics = store.create();

    store.complete(tracing, outcome("tracing"));
    store.complete(metrics, outcome("metrics"));

    expect(store.get(tracing)).toEqual(outcome("tracing"));
    expect(store.get(metrics)).toEqual(outcome("metrics"));
  });

  // A full plan per completed run, in a process meant to run indefinitely.
  it("evicts the least recently completed plan rather than growing without bound", () => {
    const store = new PlanStore();
    const ids: string[] = [];
    for (let index = 0; index < MAX_STORED_PLANS + 1; index += 1) {
      const id = store.create();
      ids.push(id);
      store.complete(id, outcome(`topic-${index}`));
    }

    expect(store.get(ids[0] as string)).toBeUndefined();
    expect(store.get(ids[1] as string)).toEqual(outcome("topic-1"));
    expect(store.get(ids[MAX_STORED_PLANS] as string)).toEqual(
      outcome(`topic-${MAX_STORED_PLANS}`),
    );
  });

  it("keeps a plan that was completed again ahead of the eviction queue", () => {
    const store = new PlanStore();
    const first = store.create();
    store.complete(first, outcome("tracing"));

    for (let index = 0; index < MAX_STORED_PLANS - 1; index += 1) {
      const id = store.create();
      store.complete(id, outcome(`filler-${index}`));
    }
    // Re-completing moves it back to the newest position, so the next two evictions take
    // filler-0 and filler-1 rather than this one.
    store.complete(first, outcome("tracing", "failed"));
    for (let index = 0; index < 2; index += 1) {
      const id = store.create();
      store.complete(id, outcome(`later-${index}`));
    }

    expect(store.get(first)).toEqual(outcome("tracing", "failed"));
  });

  it("keeps the declined status distinct from planned, not just the plan content", () => {
    const store = new PlanStore();
    const id = store.create();

    store.complete(id, outcome("kubernetes", "declined"));

    expect(store.get(id)).toEqual({
      status: "declined",
      plan: { topic: "kubernetes", weeks: [], gaps: [] },
    });
  });
});
