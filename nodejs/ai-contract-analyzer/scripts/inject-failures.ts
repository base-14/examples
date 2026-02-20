/**
 * Failure injection toolkit — demonstrates 7 failure scenarios and how each
 * produces a distinct, diagnosable trace pattern in Base14 Scout.
 *
 * Usage:
 *   bun run scripts/inject-failures.ts                   # run all scenarios
 *   bun run scripts/inject-failures.ts hallucination     # run one scenario
 *
 * The server must be running: bun run dev
 */

const BASE_URL = Bun.env["API_URL"] ?? "http://localhost:3000";
const CONTRACTS_DIR = new URL("../data/contracts/", import.meta.url).pathname;
const TEST_DIR = new URL("../data/test/", import.meta.url).pathname;

// ── helpers ──────────────────────────────────────────────────────────────────

async function uploadContract(
  filePath: string,
  inject?: Record<string, unknown>
): Promise<{ contract_id: string; overall_risk: string; trace_id: string }> {
  const file = Bun.file(filePath);
  const exists = await file.exists();
  if (!exists) throw new Error(`File not found: ${filePath}`);

  const form = new FormData();
  form.append("file", new File([await file.arrayBuffer()], file.name ?? "contract.pdf", {
    type: filePath.endsWith(".pdf") ? "application/pdf" : "text/plain",
  }));
  if (inject) {
    form.append("_inject", JSON.stringify(inject));
  }

  const res = await fetch(`${BASE_URL}/api/contracts`, { method: "POST", body: form });
  const json = await res.json();
  if (!res.ok) throw new Error(`Upload failed (${res.status}): ${JSON.stringify(json)}`);
  return json as { contract_id: string; overall_risk: string; trace_id: string };
}

function log(scenario: string, msg: string) {
  console.log(`[${scenario}] ${msg}`);
}

// ── scenario 1: hallucinated clause ──────────────────────────────────────────
// Upload a minimal 1-page contract. Model over-extracts because injection flag
// forces full extraction regardless of confidence. Scout shows clauses with
// low confidence scores and excerpts not present in source document.
async function hallucination() {
  log("hallucination", "uploading minimal NDA to force over-extraction...");
  const result = await uploadContract(`${TEST_DIR}minimal-nda.txt`, {
    force_full_extraction: true,
  });
  log("hallucination", `done — trace: ${result.trace_id}`);
  log("hallucination", "Scout: look for extraction span with confidence_avg < 0.5 and clauses flagged with present=true but no text excerpt");
}

// ── scenario 2: token overflow ────────────────────────────────────────────────
// Upload a very large document with chunking fallback disabled.
// Scout shows ingest span with total_characters > 600000, console warning,
// and the pipeline degrading gracefully.
async function tokenOverflow() {
  log("token-overflow", "uploading huge contract with chunking disabled...");
  const result = await uploadContract(`${TEST_DIR}huge-contract.txt`, {
    disable_chunking_fallback: true,
  });
  log("token-overflow", `done — trace: ${result.trace_id}`);
  log("token-overflow", "Scout: ingest span shows document.total_characters >> 600000");
}

// ── scenario 3: embedding API failure ─────────────────────────────────────────
// Inject a simulated 429 from OpenAI's embedding endpoint.
// Scout shows embed stage span with error status and EMBEDDING_FAILURE code.
// The overall pipeline aborts with contract status = error.
async function embeddingFailure() {
  log("embedding-failure", "injecting rate limit error on embedding stage...");
  try {
    await uploadContract(`${CONTRACTS_DIR}sample-nda.txt`, {
      embedding_error: "rate_limit",
    });
  } catch (err) {
    log("embedding-failure", `expected failure: ${(err as Error).message}`);
    log("embedding-failure", "Scout: embed span has SpanStatus=ERROR and http_status=429");
  }
}

// ── scenario 4: malformed / corrupted PDF ─────────────────────────────────────
// Upload a file that isn't a valid PDF. pdf-parse v2 throws; ingest stage
// records a PARSE_ERROR span with code attribute.
async function malformedPdf() {
  log("malformed-pdf", "uploading corrupted PDF...");
  try {
    await uploadContract(`${TEST_DIR}corrupted.pdf`);
  } catch (err) {
    log("malformed-pdf", `expected failure: ${(err as Error).message}`);
    log("malformed-pdf", "Scout: ingest span has SpanStatus=ERROR, document.parse_error attribute set");
  }
}

// ── scenario 5: password-protected PDF ───────────────────────────────────────
// pdf-parse v2 throws on encrypted PDFs. Same PARSE_ERROR path as corrupted.
async function encryptedPdf() {
  log("encrypted-pdf", "uploading password-protected PDF...");
  try {
    await uploadContract(`${TEST_DIR}encrypted.pdf`);
  } catch (err) {
    log("encrypted-pdf", `expected failure: ${(err as Error).message}`);
    log("encrypted-pdf", "Scout: ingest span shows PARSE_ERROR with 'encrypted' in detail");
  }
}

// ── scenario 6: batch overload / cost runaway ─────────────────────────────────
// Upload all sample contracts concurrently. gen_ai.client.cost counter spikes.
// Scout shows concurrent analyze_contract spans and total token usage.
async function batchOverload() {
  log("batch-overload", "uploading all sample contracts concurrently...");
  const { readdirSync } = await import("fs");
  let files: string[];
  try {
    files = readdirSync(CONTRACTS_DIR)
      .filter((f) => f.endsWith(".pdf") || f.endsWith(".txt"))
      .map((f) => `${CONTRACTS_DIR}${f}`);
  } catch {
    log("batch-overload", "no contracts in data/contracts/ — add some PDFs first");
    return;
  }

  if (files.length === 0) {
    log("batch-overload", "no contracts found");
    return;
  }

  log("batch-overload", `uploading ${files.length} contracts in parallel...`);
  const results = await Promise.allSettled(files.map((f) => uploadContract(f)));
  const succeeded = results.filter((r) => r.status === "fulfilled").length;
  const failed = results.filter((r) => r.status === "rejected").length;
  log("batch-overload", `done — ${succeeded} succeeded, ${failed} failed`);
  log("batch-overload", "Scout: gen_ai.client.cost counter shows spike, multiple concurrent analyze_contract spans");
}

// ── scenario 7: contradictory clauses ─────────────────────────────────────────
// Upload a contract with contradictory termination clauses.
// The score stage identifies contradictions; cross-stage validation in
// orchestrator flags disagreement between extract and score.
async function contradictoryClauses() {
  log("contradictory-clauses", "uploading contract with contradictory termination clauses...");
  const result = await uploadContract(`${TEST_DIR}contradictory-termination.txt`);
  log("contradictory-clauses", `done — overall risk: ${result.overall_risk}, trace: ${result.trace_id}`);
  log("contradictory-clauses", "Scout: score span shows both termination_for_convenience and irrevocable_agreement present");
}

// ── runner ────────────────────────────────────────────────────────────────────

const SCENARIOS: Record<string, () => Promise<void>> = {
  hallucination,
  "token-overflow": tokenOverflow,
  "embedding-failure": embeddingFailure,
  "malformed-pdf": malformedPdf,
  "encrypted-pdf": encryptedPdf,
  "batch-overload": batchOverload,
  "contradictory-clauses": contradictoryClauses,
};

const target = process.argv[2];

if (target) {
  const fn = SCENARIOS[target];
  if (!fn) {
    console.error(`Unknown scenario '${target}'. Available: ${Object.keys(SCENARIOS).join(", ")}`);
    process.exit(1);
  }
  await fn();
} else {
  console.log("Running all failure scenarios sequentially...\n");
  for (const [name, fn] of Object.entries(SCENARIOS)) {
    console.log(`\n── ${name} ──`);
    try {
      await fn();
    } catch (err) {
      console.error(`  Error: ${(err as Error).message}`);
    }
  }
  console.log("\nAll scenarios complete. Open Scout to inspect traces.");
}
