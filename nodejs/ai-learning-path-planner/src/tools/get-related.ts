import { tool } from "ai";
import { z } from "zod";
import type { CorpusStore } from "../corpus/store.ts";

const DEFAULT_LIMIT = 5;

export function getRelatedTool(store: CorpusStore) {
  return tool({
    description: "Returns corpus entries related to a known corpus path.",
    inputSchema: z.object({
      path: z.string(),
      limit: z.number().int().positive().max(20).optional(),
    }),
    execute: async ({ path, limit }) => store.related(path, limit ?? DEFAULT_LIMIT),
  });
}
