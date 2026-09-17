import { Hono } from "hono";
import type { CorpusStore } from "../corpus/store.ts";

export interface CorpusRouteDeps {
  store: CorpusStore;
}

// GET /corpus/stats returns CorpusStats exactly as CorpusStore.stats() produces it, and
// nothing else. The design's endpoint table also mentions an index build time, but the
// artifact carries no such field, and data/corpus.json.gz is committed and byte-for-byte
// reproducible - adding a timestamp anywhere in this response would mean deriving one at
// boot that was never in the artifact, which is not worth it for one extra field.
export function corpusRoutes(deps: CorpusRouteDeps): Hono {
  const corpus = new Hono();

  corpus.get("/corpus/stats", (c) => c.json(deps.store.stats(), 200));

  return corpus;
}
