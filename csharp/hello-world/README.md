# C# Hello World — OpenTelemetry

A minimal C# app that sends a **trace**, a **log**, and a **metric** to an OpenTelemetry collector. It demonstrates the three core signals of observability and how they connect.

## What You'll See in Scout

After running this app, open Scout and look for:

- **TraceX** — three spans under service `hello-world-csharp`: `say-hello` (ok), `check-disk-space` (ok), `parse-config` (error)
- **LogX** — three log entries under service `hello-world-csharp`: an Information, a Warning, and an Error with stack trace (.NET uses its own severity names) — all correlated to their traces
- **Metrics** — a `hello.count` counter

Click a log entry in LogX → **Trace Info** tab → **Open trace details** to see the trace it belongs to. This is log-trace correlation in action.

## Key Concepts

- **Span** — .NET uses `System.Diagnostics.Activity` as its tracing API; each Activity maps to an OTel span
- **Log-trace correlation** — when a log is emitted inside an Activity, it carries the span's trace ID, so you can jump between logs and traces
- **Metric** — .NET uses `System.Diagnostics.Metrics` as its metrics API; here, a simple counter tracks how many times the app runs

## Prerequisites

- .NET 9.0+
- A running OpenTelemetry collector accepting OTLP/HTTP on port 4318 (see [collector setup docs](../../scout-collector/README.md))

## Run It

```bash
# Run the app, pointing at your collector
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318 dotnet run
```

You should see:

```
Done. Check Scout for your trace, log, and metric.
```

## Verify in Scout

1. **Traces** — go to TraceX, search for service `hello-world-csharp`. You'll see three spans: `say-hello`, `check-disk-space`, and `parse-config` (marked as error with an exception).
2. **Logs** — go to LogX, search for service `hello-world-csharp`. You'll see three entries at different severity levels (Information, Warning, Error). Click any log → Trace Info → Open trace details to see the correlated trace.
3. **Metric** — look for the `hello.count` counter under service `hello-world-csharp`.

## Signals Included

| Signal | Status | Notes |
|---|---|---|
| Traces | Stable | Production-ready |
| Metrics | Stable | Production-ready |
| Logs | Stable | Production-ready |

See [OTel SDK Signal Maturity](https://opentelemetry.io/docs/languages/dotnet/) for details.
