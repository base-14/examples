import { randomUUID } from "node:crypto";
import type { LeadOutcome } from "../agents/lead.ts";

// In-memory and unpersisted: a restart loses every plan, which is documented behaviour rather
// than a gap. Bounded too, evicting the least recently completed, so a long-running process
// does not grow without limit; past the cap a GET 404s exactly as it does after a restart.
//
// Stores the full LeadOutcome, not the bare Plan. status belongs to the run, not to the plan
// document, and without it a GET after a declined POST would return a plan-shaped 200.
export const MAX_STORED_PLANS = 1024;

export class PlanStore {
  private readonly plans = new Map<string, LeadOutcome>();

  // Reserves an id before the agent has produced anything. Nothing is stored under it yet, so
  // a get() still 404s until complete() runs: there is no "pending" state to expose.
  create(): string {
    return randomUUID();
  }

  // Delete before set: Map iterates in insertion order and set() on an existing key does not
  // move it, so this keeps insertion order equal to recency order.
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
