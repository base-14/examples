import type { CorpusStore } from "./store.ts";

// The only place a plan step's citation is accepted. A path outside the loaded artifact
// is rejected outright. A heading is checked against the actual sections the store can
// serve, via fetchSection, rather than re-parsing the catalogue's headings list, so a
// validated citation is guaranteed fetchable, not merely plausible.
export function validateCitation(store: CorpusStore, path: string, heading?: string): boolean {
  if (heading !== undefined) {
    return store.fetchSection(path, heading) !== undefined;
  }
  return store.getEntry(path) !== undefined;
}
