# SNMP Telemetry

Runnable example that collects metrics from SNMP-speaking devices
(routers, switches, UPSes, printers, any net-snmp host) with the
OpenTelemetry Collector's `snmpreceiver` and ships OTLP to base14
Scout or any upstream Collector.

Three simulated devices ship with the example so it boots with a
single command — no real hardware required.

## Architecture

```text
  snmpsim (python:3.12-slim + snmpsim 1.2.1)
    ├─ community=linux-host     (HOST-RESOURCES-MIB, UCD-SNMP-MIB)
    ├─ community=cisco-router   (IF-MIB: ifTable + ifXTable)
    └─ community=apc-ups        (PowerNet-MIB, enterprise 318)
           │
           │   SNMPv2c on UDP 1161
           ▼
  otel-collector (contrib 0.149.0)
    ├─ snmp/linux   → pipeline metrics/linux
    ├─ snmp/router  → pipeline metrics/router
    └─ snmp/ups     → pipeline metrics/ups
           │
           ▼
      debug exporter  (default; swap to otlphttp for Scout)
```

## Prerequisites

- Docker Desktop / Docker Engine with Compose v2
- Optional: `snmpwalk` (net-snmp) for local verification

## Quick start

```bash
cd components/snmp-telemetry
cp .env.example .env        # edit ENVIRONMENT / SERVICE_NAMESPACE / SITE_ID
docker compose up -d
docker logs -f otel-collector
```

You'll see per-device metrics within about 30 seconds (collection
interval). Stop with `docker compose down`.

## Service identity

Each device pipeline stamps its metrics with a distinct
`service.name` so Scout shows three services:

| Device profile | service.name | device.kind |
| --- | --- | --- |
| Linux / net-snmp | `linux-host-01` | compute |
| Cisco router | `cisco-router-01` | network |
| APC UPS | `apc-ups-01` | power |

Shared across all three:

- `service.namespace` — `$SERVICE_NAMESPACE` (default `network-infra`)
- `environment` — `$ENVIRONMENT` (default `demo`)
- `site.id` — `$SITE_ID` (default `demo-site`)

## Verify the simulator

snmpsim publishes on host port `11161/udp`. Each `.snmprec` filename
becomes its SNMPv2c community string.

```bash
snmpwalk -v2c -c linux-host   -t 2 127.0.0.1:11161 1.3.6.1.2.1.1.1
snmpwalk -v2c -c cisco-router -t 2 127.0.0.1:11161 1.3.6.1.2.1.31.1.1.1.6
snmpwalk -v2c -c apc-ups      -t 2 127.0.0.1:11161 1.3.6.1.4.1.318.1.1.1.2.2
```

## Forwarding to Scout or an upstream Collector

The default exporter is `debug` so you can see metrics on stdout
immediately. To forward upstream, edit `config/otel-collector.yaml`:

1. Uncomment the `otlphttp/scout` (or `otlp/upstream`) exporter block.
2. Set the `endpoint` and, for Scout, inject a token via env:
   `authorization: "Bearer ${env:SCOUT_OTLP_TOKEN}"`.
3. Add the exporter name to each pipeline's `exporters:` list.
4. Pass the token to the Collector container, e.g.:

   ```bash
   SCOUT_OTLP_TOKEN=xxxxx docker compose up -d
   ```

   and add `environment: [SCOUT_OTLP_TOKEN]` to the `otel-collector`
   service in `docker-compose.yaml`.

## Adding a new device

1. Drop a `<name>.snmprec` file into `snmpsim/data/`. The filename
   becomes the SNMPv2c community. Each line is `OID|TAG|VALUE`
   where TAG is the ASN.1 type (`2` Integer, `4` OctetString,
   `6` OID, `64` IpAddress, `65` Counter32, `66` Gauge32,
   `67` TimeTicks, `70` Counter64). See the three shipped files
   for worked examples.
2. `docker compose restart snmpsim` to reindex.
3. Verify with `snmpwalk -v2c -c <name> -t 2 127.0.0.1:11161 <oid>`.
4. Add a new `snmp/<name>` receiver block to
   `config/otel-collector.yaml` with that community, declare metrics,
   and wire a matching pipeline with a `resource/<name>` processor
   for the constant `device.*` / `site.id` attributes.
5. `docker compose restart otel-collector`.

Real hardware plugs in the same way: set `endpoint` to the device's
`udp://<host>:161` and supply its community string or SNMPv3
credentials.

## What's collected

Full metric list with OIDs, units, and MIB source lives in the
[Scout docs page](../../docs/instrument/component/snmp.md). High level:

- **Linux host** — memory (total/available/cached/buffered),
  per-CPU utilization, 1/5/15-minute load averages, processes,
  user sessions.
- **Cisco router** — per-interface I/O bytes (Counter64),
  errors, nominal speed, admin/oper status, interface count.
- **APC UPS** — battery status/capacity/temperature/runtime,
  input voltage/frequency, output voltage/load/current/status.

Resource attributes on every metric follow the IoT Phase 0 schema:
`device.id`, `device.kind` (`compute` | `network` | `power`),
`device.manufacturer`, `device.model.identifier`, `site.id`.

## Troubleshooting

**Collector logs `no such host: snmpsim`** — the simulator isn't
running. `docker compose ps snmpsim` to check, then
`docker compose up -d snmpsim`.

**`snmpwalk` times out** — verify the host port with
`docker compose ps snmpsim`. Also check firewall / UDP reachability.

**No metrics in logs** — give it 30s (the `collection_interval`).
Check `docker logs otel-collector` for scrape errors.

**Adding a real device returns `Timeout`** — the receiver's default
`timeout: 5s` is usually enough, but slow devices or WAN links may
need `timeout: 10s` in the receiver block.

**Counter64 OIDs return `No Such Instance`** — older devices may not
support `ifXTable`. Fall back to 32-bit `ifInOctets`/`ifOutOctets`
(`1.3.6.1.2.1.2.2.1.10` / `.16`), but expect wraparound on
high-throughput interfaces.
