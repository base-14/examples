# MQTT Trace Context Propagation

End-to-end distributed tracing across an MQTT broker. A simulated sensor
publishes readings to Mosquitto with W3C trace context in the MQTT 5 user
properties; a consumer extracts that context, continues the same trace, and
calls a downstream HTTP service. The result is one connected trace in
[Base14 Scout][scout]: **producer span -> consumer span -> echo HTTP span**.

The broker itself is not instrumented (Mosquitto has no OpenTelemetry
integration). It stays "dark" in the trace, and that is fine: because the
endpoints propagate context, the spans on either side of the broker share one
`trace_id` with no gap that matters.

## Architecture

```text
producer (Python)              consumer (Python)            echo (FastAPI)
  publish span         MQTT 5     process span      HTTP       server span
  inject traceparent  --------->  extract context  ------->   (auto-instr.)
  into user props      Mosquitto  continue trace
        \                  (dark)        |                        /
         \________________ all export OTLP -> Collector -> Scout /
```

## Run it

The collector authenticates to Scout with the OAuth2 client-credentials
extension. Provide the four `SCOUT_*` values either by sourcing your Scout
config or by copying `.env.example` to `.env`.

```bash
# Option A: source your existing Scout config, then boot
set -a && . ~/.config/base14/scout-otel-config.env && set +a
docker compose up --build -d

# Option B: cp .env.example .env, fill in SCOUT_*, then `docker compose up -d`
```

Everything is online within ~30s. Tear down with `docker compose down`.

## What to look for

In the producer and consumer logs you will see matching trace IDs:

```bash
docker compose logs producer | grep trace_id   # published reading mid=.. trace_id=ABC
docker compose logs consumer | grep trace_id   # processed message .. trace_id=ABC
```

The same ID confirms the context crossed the broker. In Scout, open Traces and
find a trace with three spans: `publish sensors/sensor-001/reading` (producer),
`process sensors/sensor-001/reading` (consumer), and the echo HTTP server span
(`POST`).

To confirm trace continuity without the Scout UI, watch the collector's debug
exporter; the three spans print to stdout with the same trace ID:

```bash
docker compose logs otel-collector | grep -i "trace id"
```

## Add more devices

Run a second producer with a different identity:

```bash
docker compose run -d -e DEVICE_ID=sensor-002 producer
```

The consumer's `sensors/+/reading` subscription picks it up automatically; each
device's readings carry their own `device.id` resource attribute.

## Negative test: missing context

A message published without trace context (for example by a non-MQTT-5 client)
must not break the consumer. It starts a new root span tagged
`mqtt.missing_context=true` instead of silently dropping the message:

```bash
docker compose exec mosquitto \
  mosquitto_pub -t sensors/legacy/reading -m '{"device_id":"legacy","reading":21.0}'
```

Look for the consumer warning and a standalone trace in Scout carrying the
`mqtt.missing_context=true` attribute.

## Notes

- **QoS 1** is used so the producer span ends on the broker `PUBACK`, making its
  duration reflect the real publish round-trip. With QoS 0 there is no ack, so
  the span would end immediately after handing the packet to the client.
- **MQTT 5 is required.** MQTT 3.1.1 has no user properties; carrying trace
  context on 3.1.1 would mean encoding it into the payload, which this example
  does not do.
- No auth or TLS on the broker; this is a local demo. Production guidance
  belongs in a separate security note.

## Documentation

Full write-up:
[docs.base14.io/instrument/iot/mqtt-trace-propagation](https://docs.base14.io/instrument/iot/mqtt-trace-propagation/).
