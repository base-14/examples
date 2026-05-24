# IoT & Edge Examples

Runnable examples for instrumenting IoT devices and edge fleets with
OpenTelemetry and shipping the signals to [Base14 Scout][scout]. Every
example runs locally with Docker, no cloud account required.

The track builds a single story across five phases. Each phase adds one
self-contained example and reuses the pieces the earlier phases stood
up, so the recommended path is to work through them in order.

## Progression

| Phase | Example | What it demonstrates | Status |
| --- | --- | --- | --- |
| 1 | [`mqtt-trace-propagation/`](./mqtt-trace-propagation) | Trace context carried across an MQTT 5 broker (Mosquitto) via user properties: a publisher and subscriber service emit OTLP, and Scout stitches them into one end-to-end trace. | Available |
| 2 | [`edge-collector-store-forward/`](./edge-collector-store-forward) | An edge Collector with disk-buffered store-and-forward, interval downsampling, priority routing, and a battery-aware filter, surviving simulated network disconnects. | Available |
| 3 | `opcua-bridge/` | A bridge service that subscribes to an OPC-UA simulator and emits OTLP metrics with industrial resource attributes, standing in for the absent contrib receiver. | Coming soon |
| 4 | `sparkplug-bridge/` | A decoder that turns Sparkplug B NBIRTH / DBIRTH / DDATA messages into OTLP metrics with device lifecycle state. | Coming soon |
| 5 | `esp32-firmware/` | Constrained-device firmware emitting a compact payload over MQTT, converted to OTLP by an edge Collector that reuses the Phase 1 and Phase 2 building blocks. | Coming soon |

## Sequencing

- Phase 1 (MQTT trace propagation) is the foundation; Phases 4 and 5
  build on it.
- Phase 2 (edge Collector) is reused by Phase 5.
- Phases 3 and 4 are independent of each other.

## Pinned minimums

These are fixed for the whole track so the examples stay consistent.
Individual phases may revisit a pin if a dependency requires it, and
will say so in their own README.

- **Docker Compose:** v2.24+ (the `include:` directive that later
  phases use to reuse the Phase 1 Mosquitto service). Podman Compose
  4.7+ also supports `include:`.
- **Python:** 3.13 (some dependencies still lag on 3.14).
- **OpenTelemetry Collector contrib:** 0.152.0 (bumped track-wide as a
  single update when needed).
- **OpenTelemetry Python SDK:** 1.41.0 / instrumentation 0.62b0. Note
  that `BatchLogRecordProcessor`'s default schedule delay changed from
  5000ms to 1000ms in this release; set it explicitly if a phase needs
  the older cadence.

## Documentation

The companion guides live at
[docs.base14.io/instrument/iot](https://docs.base14.io/instrument/iot/),
including the shared `device.*` / `fleet.*` / `asset.*` resource
attribute conventions every example here follows.

[scout]: https://base14.io
