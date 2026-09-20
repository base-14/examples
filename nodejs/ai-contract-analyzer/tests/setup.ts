/**
 * Test setup, run by vitest before every test file.
 *
 * Importing ./telemetry.ts registers the in-memory tracer and meter providers,
 * so instruments created at module load bind to them. No provider API keys are
 * set: the tests never reach a hosted provider.
 */
import "./telemetry.ts";

process.env.OTEL_ENABLED = "false";
process.env.DATABASE_URL =
  process.env.DATABASE_URL ??
  "postgresql://postgres:postgres@localhost:5434/contract_analyzer_test";
