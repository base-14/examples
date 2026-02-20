/**
 * Test setup — disables OTel and provides LLM mock helpers.
 *
 * Import this at the top of test files or configure via vitest.config.ts.
 * OTel is disabled by setting OTEL_ENABLED=false before any imports.
 */

// Disable telemetry in tests — prevents OTel SDK from trying to connect
process.env.OTEL_ENABLED = "false";
process.env.DATABASE_URL =
  process.env.DATABASE_URL ??
  "postgresql://postgres:postgres@localhost:5434/contract_analyzer_test";
process.env.ANTHROPIC_API_KEY = process.env.ANTHROPIC_API_KEY ?? "test-key";
process.env.OPENAI_API_KEY = process.env.OPENAI_API_KEY ?? "test-key";

export {};
