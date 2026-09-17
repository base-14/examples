import type { CorpusStore } from "./store.ts";

// The only place a plan step's citation is accepted. Headings are checked through
// fetchSection, not against the catalogue's heading list, so a validated citation is
// fetchable rather than merely plausible.
export function validateCitation(store: CorpusStore, path: string, heading?: string): boolean {
  if (heading !== undefined) {
    return store.fetchSection(path, heading) !== undefined;
  }
  return store.getEntry(path) !== undefined;
}
