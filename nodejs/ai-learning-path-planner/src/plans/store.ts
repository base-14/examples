import { randomUUID } from "node:crypto";
import type { LeadOutcome } from "../agents/lead.ts";

// An in-memory map with no persistence. A restart loses every plan ever completed, which
// is the documented behaviour, not a gap: the corpus is read-only and a plan is cheap to
// regenerate, so nothing here is worth a database.
//
// Bounded, though, and for the reason telemetry/enrich.ts bounds the cost accumulator: a
// full plan per completed run, in a process meant to run indefinitely, is a map that only
// ever grows. Eviction is least recently completed, so the ids a caller is most likely to
// GET are the ones that survive. Past the cap a GET answers 404 the same way it does after
// a restart, which is a case the endpoint and the README already describe.
//
// Stores the full LeadOutcome ({status, plan}), not the bare Plan. PlanSchema itself stays
// {topic, weeks, gaps} - status belongs to the run, not to the plan document, and the lead
// agent's structured-output contract has no business reporting its own decline. Without
// carrying status here, a GET after a declined POST would return a plan-shaped body
// indistinguishable from a real one, at 200, after the POST already answered 422.
export const MAX_STORED_PLANS = 1024;

export class PlanStore {
  private readonly plans = new Map<string, LeadOutcome>();

  // Reserves an id before the lead agent has produced anything. Nothing is stored under
  // it yet, so a get() against a freshly created id still 404s until complete() runs -
  // there is no separate "pending" status to expose, only "not found yet" and "found".
  create(): string {
    return randomUUID();
  }

  // Deleting before setting keeps insertion order the same as recency order, so the first
  // key is always the least recently completed one. Map iterates in insertion order and a
  // plain set() on an existing key does not move it.
  complete(id: string, outcome: LeadOutcome): void {
    if (this.plans.delete(id) === false && this.plans.size >= MAX_STORED_PLANS) {
      const oldest = this.plans.keys().next().value;
      if (oldest !== undefined) {
        this.plans.delete(oldest);
      }
    }
    this.plans.set(id, outcome);
  }

  get(id: string): LeadOutcome | undefined {
    return this.plans.get(id);
  }
}
