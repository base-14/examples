# Ruby Hello World — OpenTelemetry (Traces Only)

A minimal Ruby app that sends **traces** to an OpenTelemetry collector. It demonstrates spans, span events, and error recording.

> **Note**: Ruby's OTel metrics and logs SDKs are still in development (0.x). This example covers traces only. See [OTel SDK Signal Maturity](https://opentelemetry.io/docs/languages/ruby/) for the latest status.

## What You'll See in Scout

After running this app, open Scout and look for:

- **TraceX** — three spans under service `hello-world-ruby`: `say-hello` (ok), `check-disk-space` (ok), `parse-config` (error)
- Span events on `say-hello` and `check-disk-space` — these are timestamped annotations that serve as in-span log equivalents

Click a span to see its events, attributes, and (for `parse-config`) the recorded exception with stack trace.

## Key Concepts

- **Span** — a unit of work your app performs, with a start time, duration, and status
- **Span event** — a timestamped annotation on a span (used here in place of logs, since the Ruby logs SDK is not yet stable)
- **Exception recording** — attaching error details and stack traces to a span

## Prerequisites

- Ruby 3.1+
- Bundler
- A running OpenTelemetry collector accepting OTLP/HTTP on port 4318 (see [collector setup docs](../../scout-collector/README.md))

## Run It

```bash
# Install dependencies
bundle install

# Run the app, pointing at your collector
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318 ruby main.rb
```

You should see:

```
Done. Check Scout for your traces.
```

## Verify in Scout

1. **Traces** — go to TraceX, search for service `hello-world-ruby`. You'll see three spans: `say-hello`, `check-disk-space`, and `parse-config` (marked as error with an exception).
2. **Span events** — click `say-hello` or `check-disk-space` to see their events.

## Signals Included

| Signal | Status | Notes |
|---|---|---|
| Traces | Stable | Production-ready |
| Metrics | Not included | SDK in development (0.x) |
| Logs | Not included | SDK in development (0.x) |

See [OTel SDK Signal Maturity](https://opentelemetry.io/docs/languages/ruby/) for details.
