import { tool } from "ai";
import { z } from "zod";
import type { CorpusStore } from "../corpus/store.ts";

// The largest single file in the shipped corpus is 121,025 characters, roughly 30,000
// tokens at the four-characters-per-token convention this example uses elsewhere, against
// an OLLAMA_NUM_CTX of 16,384. One uncapped call could therefore return about 1.8 times
// the whole context window, which Ollama answers with done_reason "length" and no content
// and the run surfaces as "No output generated". The cap is set at the same order as the
// largest result fetch_section can already produce from this corpus, 25,503 characters, so
// nothing that fitted before is truncated now. A fixed cap rather than a limit parameter,
// so the model cannot opt out of it and the tool definition keeps its measured size.
const MAX_TEXT_CHARS = 24_000;

// The name says example and the behaviour is wider: CorpusStore.fetchExampleFile serves
// any path in the corpus, docs pages included, and a researcher legitimately needs both.
// The behaviour is the right one, so the description says so rather than the tool being
// narrowed to match its name. Kept to the same character count as the wording it replaced,
// because base14.gen_ai.tool_definition.tokens is the definition's characters over four and
// the published 361 and 650 estimates derive from it.
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
