# Scout MCU Envelope v1 (SME-v1)

A compact JSON envelope a constrained device publishes over MQTT when it
cannot run a full OTLP/protobuf + TLS stack. The `sme-bridge` service
parses it and emits OTLP to a Collector, so the device stays small while
the telemetry still lands in Scout as ordinary OpenTelemetry signals.

SME-v1 is deliberately the replaceable piece. The wire format is not
OTLP, the bridge is what makes it OTel. A team that wants strict
wire-level OTLP can swap the envelope for OTLP-protobuf (see the nanopb
appendix in the docs) and keep everything downstream.

## Transport

- One envelope per MQTT message, published to
  `{prefix}/{device_id}/telemetry` (default prefix `scout/mcu`).
- The device sets an MQTT Last Will on `{prefix}/{device_id}/offline`
  so the broker announces an ungraceful disconnect. The payload is a
  small JSON object, `{"v":1,"device":{...},"reason":"lwt"}`.
- QoS 1 for both, so a single dropped packet does not lose a reading.

## Envelope

```json
{
  "v": 1,
  "device": {
    "id": "esp32-dev-01",
    "model": "esp32-s3-devkitc",
    "firmware": { "version": "0.1.0", "channel": "dev" },
    "fleet": { "id": "fleet-demo", "tenant": "acme" }
  },
  "ts_ms": 1712347200000,
  "ts_source": "sntp",
  "trace": { "traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01" },
  "metrics": [
    { "name": "mcu.cpu.temp_c", "kind": "gauge",   "value": 42.1,  "unit": "Cel" },
    { "name": "mcu.uptime",     "kind": "counter", "value": 12345, "unit": "s" }
  ],
  "events": [
    { "name": "wifi.reconnect", "severity": "warn", "attrs": { "rssi": -78 } }
  ]
}
```

## Fields

| Field | Required | Meaning |
| --- | --- | --- |
| `v` | yes | Envelope version. The bridge rejects any value it does not know. |
| `device.id` | yes | Stable device identifier. Becomes the MQTT topic segment and `device.id`. |
| `device.model` | no | Hardware model, becomes `device.model.identifier`. |
| `device.firmware.version` | no | Running firmware version, becomes `device.firmware.version`. |
| `device.firmware.channel` | no | Release channel (`dev` / `beta` / `stable`), becomes `device.firmware.channel`. |
| `device.fleet.id` | no | Fleet membership, becomes `fleet.id`. |
| `device.fleet.tenant` | no | Owning tenant, becomes `fleet.tenant`. |
| `ts_ms` | yes | Reading time, Unix milliseconds. |
| `ts_source` | no | `sntp` once time is synced, else `uptime`. Becomes `mcu.ts_source` on each datapoint so downstream can reason about clock reliability. |
| `trace.traceparent` | no | W3C trace context for the publish. Present when the device wants a specific operation correlated. |
| `metrics[]` | no | Zero or more readings (see below). |
| `events[]` | no | Zero or more events (see below). |

### Metrics

| Field | Required | Meaning |
| --- | --- | --- |
| `name` | yes | Instrument name, used verbatim (no rewriting). |
| `kind` | yes | `gauge` (a level) or `counter` (a monotonic cumulative total). |
| `value` | yes | Numeric value. |
| `unit` | no | UCUM unit, e.g. `Cel`, `s`, `By`. |

`gauge` becomes an OTel gauge. `counter` becomes a monotonic Sum, so it
stays rate-able even though the device sends the running total.

### Events

| Field | Required | Meaning |
| --- | --- | --- |
| `name` | yes | Event name, becomes the log body. |
| `severity` | no | `debug` / `info` / `warn` / `error`. Defaults to `info`. |
| `attrs` | no | Flat map of string or number attributes, attached to the log record. |

## Resource mapping

The `device` block maps to the track's resource attributes. The bridge
builds one OTel `Resource` per device and adds `device.kind=mcu`:

| Envelope | Resource attribute |
| --- | --- |
| `device.id` | `device.id` |
| `device.model` | `device.model.identifier` |
| `device.firmware.version` | `device.firmware.version` |
| `device.firmware.channel` | `device.firmware.channel` |
| `device.fleet.id` | `fleet.id` |
| `device.fleet.tenant` | `fleet.tenant` |
| (constant) | `device.kind=mcu` |

## Versioning rules

- `v` is a single integer. Increment it for any breaking change to the
  shape (renamed or removed fields, changed semantics).
- Additive, backward-compatible fields do not bump `v`. A bridge reading
  `v: 1` must ignore unknown fields rather than fail.
- The bridge accepts only the versions it implements and counts the rest
  under `sme_bridge.version_rejected_total`. It never guesses.
