# OPC-UA to OTel Bridge

OPC-UA is the dominant protocol on the factory floor, and the OpenTelemetry
Collector has no receiver for it. This example is the bridge: a small Python
service subscribes to an OPC-UA server, maps each node to an OTLP metric using
a declarative `node_map.yaml`, turns pump status changes into fault logs, and
wraps each session in a span so reconnects are visible. A simulated factory
server (asyncua) drives realistic readings and periodic pump faults so there is
something to watch end to end.

## Architecture

```text
 opcua-net
 ┌──────────────┐   OPC-UA      ┌──────────────┐  OTLP   ┌──────────────────┐
 │ opcua-server │   binary      │ bridge       │ ──────> │ otel-collector   │ OTLP
 │ (asyncua)    │ ────────────> │ (subscribe,  │         │ (oauth2 -> b14)  │ ───> Scout
 │ factory sim  │   :4840       │  map, log)   │         └──────────────────┘
 └──────────────┘               └──────────────┘
   6 nodes                       5 metrics + fault logs + session spans
```

The server simulates one production line: a transfer pump (flow, vibration,
status), an infeed conveyor (speed), a cure oven (temperature), and a line
throughput counter. Every `FAULT_INTERVAL_S` the pump faults for
`FAULT_DURATION_S` - flow and conveyor speed drop to zero, vibration spikes,
and status flips to `fault` - then recovers.

## What the bridge does

1. **Declarative node mapping** - `bridge/node_map.yaml` lists each OPC-UA node
   with its OTLP metric name, unit, kind (`gauge` / `counter` / `status`), and
   `asset.*` attributes. No code change to add or remap a node.
2. **Observable metrics** - each gauge/counter is an OTel observable instrument
   whose callback reads the node's latest value from a cache the subscription
   handler keeps current. Five metrics emit; the sixth node is the pump status.
3. **Fault logs** - a `status` node is not a metric. When the pump status
   changes, the bridge emits an OTLP log record (`asset entered fault state` /
   `asset recovered`) carrying the asset attributes.
4. **Session spans** - the OPC-UA session lifecycle is one `opcua.session`
   span. It ends when the connection drops, so a server restart produces a
   completed span and the bridge reconnects with a fresh one - reconnects show
   up as a sequence of spans.

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

The bridge connects once the server health check passes. Tear down with
`docker compose down`.

## See a fault sooner

The default fault cycle is every 10 minutes. Shorten it to watch a fault land
within a minute:

```bash
set -a && . ~/.config/base14/scout-otel-config.env && set +a
FAULT_INTERVAL_S=25 FAULT_DURATION_S=10 docker compose up --build -d
docker compose logs -f bridge   # watch for "asset entered fault state"
```

In Scout, `factory.pump.flow_rate` drops to zero, `factory.pump.vibration_rms`
spikes, and a fault log record appears with `asset.id=pump-1`.

## Reconnect test

```bash
docker compose restart opcua-server
docker compose logs -f bridge
```

The bridge logs the dropped session and reconnects within ~1s (exponential
backoff starts at 1s, caps at 30s). The ended session span exports right after,
so the reconnect is one completed `opcua.session` span in Scout.

## Mapping a node

Add an entry to `bridge/node_map.yaml`; no code change:

```yaml
- node_id: "ns=2;s=Oven1/TempC"
  metric:
    name: factory.oven.temp_c
    unit: "Cel"
    kind: gauge          # gauge | counter | status
    description: Oven zone temperature
  attributes:
    asset.id: oven-1
    asset.type: oven
    asset.name: Cure Oven 1
    asset.parent_id: line-1
```

`kind: status` makes the node a fault-log source instead of a metric. Asset
hierarchy is expressed with `asset.parent_id` chains, following the
[locked IoT resource schema](https://docs.base14.io/instrument/iot/).

## Caveats

- **No OPC-UA security** - the demo server runs `NoSecurity` and the bridge
  connects anonymously. A real deployment uses a security policy plus
  certificate or username auth; that is a config change on both ends, out of
  scope here.
- **Bridge, not receiver** - this is application code standing in for a
  Collector receiver that does not exist. The pattern (subscribe, cache,
  observable callbacks, declarative map) is what we are proposing upstream.
- **Polling liveness** - the bridge issues a periodic `read_value()` to detect
  a silently dropped connection; the subscription alone will not always raise
  on a half-open socket.
- **Demo simplifications** - one server, one line, no TLS between bridge and
  collector. All belong in a production hardening pass.

## Documentation

Full write-up:
[docs.base14.io/instrument/iot/opcua](https://docs.base14.io/instrument/iot/opcua/).
