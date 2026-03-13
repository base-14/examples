# Rust Hello World — OpenTelemetry

A minimal Rust app that sends a **trace**, a **log**, and a **metric** to an OpenTelemetry collector. It demonstrates the three core signals of observability and how they connect.

## What You'll See in Scout

After running this app, open Scout and look for:

- **TraceX** — three spans under service `hello-world-rust`: `say-hello` (ok), `check-disk-space` (ok), `parse-config` (error)
- **LogX** — log entries under service `hello-world-rust`: INFO, WARN, and ERROR — correlated to their traces via the `tracing` bridge
- **Metrics** — a `hello.count` counter

Click a log entry in LogX → **Trace Info** tab → **Open trace details** to see the trace it belongs to. This is log-trace correlation in action.

## Key Concepts

- **Span** — a unit of work your app performs, with a start time, duration, and status
- **Log-trace correlation** — Rust uses a bridge pattern: the `tracing` crate emits logs, and the `opentelemetry-appender-tracing` bridge forwards them to the collector with the active span's trace ID
- **Metric** — a numeric measurement (here, a simple counter that tracks how many times the app runs)

## Prerequisites

- Rust 1.75+
- A running OpenTelemetry collector accepting OTLP/HTTP on port 4318 (see [collector setup docs](../../scout-collector/README.md))

## Run It

```bash
# Build and run the app, pointing at your collector
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318 cargo run
```

You should see:

```
Done. Check Scout for your trace, log, and metric.
```

## Verify in Scout

1. **Traces** — go to TraceX, search for service `hello-world-rust`. You'll see three spans: `say-hello`, `check-disk-space`, and `parse-config` (marked as error with an exception).
2. **Logs** — go to LogX, search for service `hello-world-rust`. You'll see entries at different severity levels (INFO, WARN, ERROR). Click any log → Trace Info → Open trace details to see the correlated trace.
3. **Metric** — look for the `hello.count` counter under service `hello-world-rust`.

## Signals Included

| Signal | Status | Notes |
|---|---|---|
| Traces | Beta | All 0.x versions, but functional |
| Metrics | Stable | Production-ready |
| Logs | Stable (Bridge) | Uses `tracing` crate bridge via `opentelemetry-appender-tracing` |

See [OTel SDK Signal Maturity](https://opentelemetry.io/docs/languages/rust/) for details.
