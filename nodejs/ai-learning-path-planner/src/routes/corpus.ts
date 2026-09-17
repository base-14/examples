import { Hono } from "hono";
import type { CorpusStore } from "../corpus/store.ts";

export interface CorpusRouteDeps {
  store: CorpusStore;
}

// CorpusStats exactly as CorpusStore.stats() produces it. No build timestamp: the artifact is
// committed and byte-for-byte reproducible, and carries no such field.
export function corpusRoutes(deps: CorpusRouteDeps): Hono {
  const corpus = new Hono();

  corpus.get("/corpus/stats", (c) => c.json(deps.store.stats(), 200));

  return corpus;
}
