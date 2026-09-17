import { tool } from "ai";
import { z } from "zod";
import type { CorpusStore } from "../corpus/store.ts";

// The largest file in the corpus is several times OLLAMA_NUM_CTX, and one uncapped call
// overruns the window, which comes back as "No output generated". The cap is the same order as
// the largest result fetch_section can already produce, so nothing that fitted is truncated
// now. Fixed rather than a limit parameter, so the model cannot opt out of it.
const MAX_TEXT_CHARS = 24_000;

// The name says example, the behaviour is wider: this serves any corpus path, docs included,
// which is what a researcher needs. The description says so rather than the tool being
// narrowed to its name.
export function fetchExampleFileTool(store: CorpusStore) {
  return tool({
    description: "Fetches the full text of one file at any corpus path, an example or a doc.",
    inputSchema: z.object({ path: z.string() }),
    execute: async ({ path }) => {
      const text = store.fetchExampleFile(path);
      if (text === undefined) {
        return { path, found: false as const, text: undefined, truncated: false as const };
      }
      if (text.length <= MAX_TEXT_CHARS) {
        return { path, found: true as const, text, truncated: false as const };
      }
      return {
        path,
        found: true as const,
        text: text.slice(0, MAX_TEXT_CHARS),
        truncated: true as const,
        note:
          `Truncated: this file is ${text.length} characters and the first ${MAX_TEXT_CHARS} ` +
          "are shown. Use outline to list its headings and fetch_section to read one of them.",
      };
    },
  });
}
