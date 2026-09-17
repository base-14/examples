import { describe, expect, it } from "vitest";
import { loadConfig } from "../../src/config.ts";
import {
  COST_BOUNDARIES_USD,
  DURATION_BOUNDARIES_SECONDS,
  FANOUT_BOUNDARIES,
} from "../../src/telemetry/metrics.ts";

// A histogram boundary is only ever right or wrong about real runs, so these are the durations
// and costs observed from the containerised service on its shipped defaults.
const PLANNED_SECONDS = [72.7, 82.7, 89.9, 105.6, 131.7, 152.3];
const DECLINED_SECONDS = 0.019;
const COSTS_USD = [0.001599, 0.003011, 0.00214];

// The index of the bucket a value falls in, counting the overflow bucket above the last
// boundary. OTel histogram buckets are (previous, boundary].
function bucketOf(value: number, boundaries: number[]): number {
  const index = boundaries.findIndex((boundary) => value <= boundary);
  return index === -1 ? boundaries.length : index;
}

function bucketWidth(value: number, boundaries: number[]): number {
  const index = bucketOf(value, boundaries);
  const lower = index === 0 ? 0 : (boundaries[index - 1] as number);
  const upper = boundaries[index] ?? Number.POSITIVE_INFINITY;
  return upper - lower;
}

describe("base14.plan.duration boundaries", () => {
  it("spreads the planned band across at least four buckets", () => {
    const buckets = PLANNED_SECONDS.map((seconds) =>
      bucketOf(seconds, DURATION_BOUNDARIES_SECONDS),
    );

    expect(new Set(buckets).size).toBeGreaterThanOrEqual(4);
  });

  it("lands every planned run in a bucket no wider than thirty seconds", () => {
    for (const seconds of PLANNED_SECONDS) {
      expect(bucketWidth(seconds, DURATION_BOUNDARIES_SECONDS)).toBeLessThanOrEqual(30);
    }
  });

  it("separates a declined run from every planned one", () => {
    const declined = bucketOf(DECLINED_SECONDS, DURATION_BOUNDARIES_SECONDS);

    for (const seconds of PLANNED_SECONDS) {
      expect(bucketOf(seconds, DURATION_BOUNDARIES_SECONDS)).toBeGreaterThan(declined);
    }
  });

  it("keeps the planned band off the overflow bucket, so a slow run is still visible", () => {
    for (const seconds of PLANNED_SECONDS) {
      expect(bucketOf(seconds, DURATION_BOUNDARIES_SECONDS)).toBeLessThan(
        DURATION_BOUNDARIES_SECONDS.length,
      );
    }
  });
});

describe("base14.plan.cost boundaries", () => {
  it("prices a planned run mid-scale, so a regression has buckets to move through", () => {
    for (const cost of COSTS_USD) {
      const bucket = bucketOf(cost, COST_BOUNDARIES_USD);
      expect(bucket).toBeGreaterThan(0);
      expect(bucket).toBeLessThan(COST_BOUNDARIES_USD.length - 1);
    }
  });
});

describe("base14.plan.fanout boundaries", () => {
  // Read off the shipped default rather than restated, so raising MAX_SUBTOPICS past the
  // top boundary fails here instead of quietly putting every capped run in the overflow
  // bucket. research_subtopic counts a subtopic only once the cap has let it through, so
  // the default cap is also the largest fan-out the shipped configuration can produce.
  const DEFAULT_MAX_SUBTOPICS = loadConfig({}).maxSubtopics;

  it("gives every fan-out below the top boundary its own bucket", () => {
    for (let fanout = 0; fanout < FANOUT_BOUNDARIES.length - 1; fanout += 1) {
      expect(bucketOf(fanout, FANOUT_BOUNDARIES)).toBe(fanout);
    }
  });

  it("keeps a run at the default cap off the overflow bucket", () => {
    expect(bucketOf(DEFAULT_MAX_SUBTOPICS, FANOUT_BOUNDARIES)).toBeLessThan(
      FANOUT_BOUNDARIES.length,
    );
  });

  it("separates a declined run's zero from any run that researched something", () => {
    expect(bucketOf(0, FANOUT_BOUNDARIES)).toBe(0);
    expect(bucketOf(1, FANOUT_BOUNDARIES)).toBeGreaterThan(0);
  });
});
