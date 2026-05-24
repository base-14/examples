# Sparkplug B to OTel Bridge

Sparkplug B is the structured MQTT payload spec that dominates IIoT, and the
OpenTelemetry Collector has no decoder for it. This example is the bridge: a
Tahu-style simulator publishes a realistic Sparkplug lifecycle (NBIRTH,
DBIRTH, DDATA, DDEATH) for one edge node and two devices, and a decoder
subscribes, decodes the protobuf, tracks edge-node and device state, resolves
the metric aliases that DATA messages carry, and emits OTLP metrics plus
lifecycle log events to Scout.

## Architecture

```text
 spb-net
 ┌──────────────┐  spBv1.0/#   ┌──────────────┐         ┌──────────────┐  OTLP   ┌──────────────────┐
 │ simulator    │  over MQTT   │ mosquitto    │subscribe │ decoder      │ ──────> │ otel-collector   │ OTLP
 │ (Tahu-style) │ ───────────> │ broker       │ ───────> │ decode +     │         │ (oauth2 -> b14)  │ ───> Scout
 │ 1 node/2 dev │              │              │          │ resolve      │         └──────────────────┘
 └──────────────┘              └──────────────┘          └──────────────┘
   NBIRTH/DBIRTH/DDATA           Last Will = NDEATH        8 metric streams + lifecycle logs
```

## Sparkplug B in one minute

Topic structure is `spBv1.0/{group}/{message_type}/{edge_node}/{device?}`.
The message types that carry telemetry:

- **NBIRTH / DBIRTH** - an edge node or device comes online and advertises
  every metric with a `name`, `datatype`, and a numeric `alias`.
- **NDATA / DDATA** - metric updates that reference metrics by `alias` only,
  to save bytes. You must have seen the BIRTH to resolve them.
- **NDEATH / DDEATH** - the node or device went away. NDEATH is the broker's
  MQTT Last Will, so it fires even on an ungraceful drop.

Every payload from an edge node carries a `seq` number (0-255, wrapping). A
jump means messages were lost.

## What the decoder does

1. **Alias resolution** - on BIRTH it records `alias -> (name, datatype)` per
   device; on DATA it resolves each alias back to a named metric. An alias
   with no prior BIRTH is counted as `sparkplug.decoder.alias_unresolved_total`.
2. **Dynamic instruments** - Sparkplug metric sets are runtime-defined by
   BIRTH, so OTel instruments are created on first sight. Doubles and booleans
   become gauges; integers whose name looks monotonic (Throughput / `*Counter`
   / `*Total`) become observable counters so they stay rate-able.
3. **Lifecycle as logs** - BIRTH/DEATH are state transitions, not operations,
   so they are emitted as OTel log records (INFO on birth, WARN on death) with
   the asset attributes, not spans.
4. **Sequence tracking** - the per-edge-node `seq` is checked for continuity
   (wrap-aware); a gap increments `sparkplug.decoder.seq_gap_total`.

## Run it

The collector authenticates to Scout with the OAuth2 client-credentials
extension. Provide the four `SCOUT_*` values either by sourcing your Scout
config or by copying `.env.example` to `.env`.

```bash
# Source your Scout config, then boot (re-source it for every compose
# command - the file uses :? guards that compose re-evaluates each time).
set -a && . ~/.config/base14/scout-otel-config.env && set +a
docker compose up --build -d
```

The decoder reports healthy only once it has subscribed, and the simulator
waits for that - so the edge-node BIRTHs are never published before the
decoder is listening. The protobuf bindings (`sparkplug_b_pb2.py`) are
generated from `proto/sparkplug_b.proto` at build time and are not checked in.
Tear down with `docker compose down`.

## Exercise the state machine

```bash
set -a && . ~/.config/base14/scout-otel-config.env && set +a

# Cycle Machine2 (DDEATH then DBIRTH) every 30s to watch lifecycle events:
DEVICE_CYCLE_S=30 docker compose up --build -d

# Drop every 5th DDATA to force sequence gaps:
DROP_EVERY_N=5 docker compose up -d --force-recreate simulator

# Fire NDEATH via the broker Last Will (ungraceful stop):
docker kill spb-simulator
```

In Scout you will see `sparkplug.decoder.seq_gap_total` climb under
`DROP_EVERY_N`, an `edge node offline` (WARN) log on the kill, and
`device offline` / `device online` logs on each cycle.

## Metric mapping

Sparkplug metrics become OTel instruments named `sparkplug.<snake_case>`:

| Sparkplug metric | Datatype | OTel instrument | Unit |
| --- | --- | --- | --- |
| Temperature | Double | gauge | Cel |
| VibrationRMS | Double | gauge | mm/s |
| RunState | Boolean | gauge (0/1) | - |
| Throughput | Int64 | counter (monotonic Sum) | {item} |

Each datapoint carries `asset.id` (device), `asset.type=sparkplug_device`,
and `asset.parent_id` (edge node); `site.id` (the Sparkplug group) and
`fleet.id` are on the resource. This follows the
[locked IoT resource schema](https://docs.base14.io/instrument/iot/) -
hierarchy via `asset.parent_id`, no ad-hoc `asset.group` / `asset.edge_node`.

## Point it at a real plant

Set `MQTT_HOST` / `MQTT_PORT` on the decoder to your Sparkplug broker and
remove the simulator. The decoder subscribes to `spBv1.0/#` and decodes any
conformant Sparkplug B traffic. If it starts mid-stream and sees DATA before a
BIRTH, those aliases stay unresolved until the next BIRTH - see Caveats.

## Caveats

- **Late subscriber** - a consumer that starts after an edge node's BIRTH
  sees alias-only DATA it cannot resolve. This demo solves it for cold start
  by gating the simulator on the decoder's readiness. In production a Sparkplug
  *host application* would request a rebirth (NCMD `Node Control/Rebirth`); this
  decoder is a read-only subscriber and does not issue commands.
- **Commands out of scope** - NCMD / DCMD are control messages; the decoder
  ignores them. It is not a Sparkplug host or primary application.
- **No retained births** - per the Sparkplug spec, BIRTHs are not retained, so
  recovery relies on a rebirth, not on the broker replaying state.
- **Demo simplifications** - anonymous broker, no TLS, aliases assigned
  statically in the simulator. All belong in a production hardening pass.

## Documentation

Full write-up:
[docs.base14.io/instrument/iot/sparkplug](https://docs.base14.io/instrument/iot/sparkplug/).
