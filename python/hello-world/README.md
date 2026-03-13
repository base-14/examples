# Python Hello World — OpenTelemetry

A minimal Python app that sends a **trace**, a **log**, and a **metric** to an OpenTelemetry collector. It demonstrates the three core signals of observability and how they connect.

## What You'll See in Scout

After running this app, open Scout and look for:

- **TraceX** — three spans under service `hello-world-python`: `say-hello` (ok), `check-disk-space` (ok), `parse-config` (error)
- **LogX** — three log entries under service `hello-world-python`: an INFO, a WARNING, and an ERROR with stack trace — all correlated to their traces
- **Metrics** — a `hello.count` counter

Click a log entry in LogX → **Trace Info** tab → **Open trace details** to see the trace it belongs to. This is log-trace correlation in action.

## Key Concepts

- **Span** — a unit of work your app performs, with a start time, duration, and status
- **Log-trace correlation** — when a log is emitted inside a span, it carries the span's trace ID, so you can jump between logs and traces
- **Metric** — a numeric measurement (here, a simple counter that tracks how many times the app runs)

## Prerequisites

- Python 3.9+
- A running OpenTelemetry collector accepting OTLP/HTTP on port 4318 (see [collector setup docs](../../scout-collector/README.md))

## Run It

```bash
# Create a virtualenv and install dependencies
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Run the app, pointing at your collector
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318 python main.py
```

You should see:

```
Done. Check Scout for your trace, log, and metric.
```

## Verify in Scout

1. **Traces** — go to TraceX, search for service `hello-world-python`. You'll see three spans: `say-hello`, `check-disk-space`, and `parse-config` (marked as error with an exception).
2. **Logs** — go to LogX, search for service `hello-world-python`. You'll see three entries at different severity levels (INFO, WARNING, ERROR). Click any log → Trace Info → Open trace details to see the correlated trace.
3. **Metric** — look for the `hello.count` counter under service `hello-world-python`.

## Signals Included

| Signal | Status | Notes |
|---|---|---|
| Traces | Stable | Production-ready |
| Metrics | Stable | Production-ready |
| Logs | Development | Functional, but API may change in future SDK releases |

See [OTel SDK Signal Maturity](https://opentelemetry.io/docs/languages/python/) for details.
