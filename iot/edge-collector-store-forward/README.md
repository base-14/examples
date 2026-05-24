# Edge Collector: Store-and-Forward + Downsampling

A production-shaped edge Collector for IoT: it buffers telemetry to a
disk-backed queue so a backhaul outage loses nothing, downsamples chatty
gauges to save bandwidth, routes high-priority fleets through at full
resolution, and drops non-critical metrics when a device's battery is low.
It is pure Collector configuration - the only application change is that the
Phase 1 sensor now emits a temperature gauge to give the edge something to
downsample.

This builds directly on
[mqtt-trace-propagation](../mqtt-trace-propagation/): the same producer,
consumer, broker, and echo service are the traffic generators, repointed at
the edge Collector.

## Architecture

```text
 devices (edge-net)            edge-net          backhaul-net
 ┌──────────────┐          ┌──────────────┐    ┌──────────────────┐
 │ producer     │  OTLP    │ edge         │OTLP│ upstream         │ OTLP
 │ consumer     │ ───────> │ collector    │───>│ collector        │ ───> Scout
 │ echo         │          │              │    │ (oauth2 -> b14)  │
 │ mosquitto    │          │ disk queue   │    └──────────────────┘
 └──────────────┘          └──────────────┘
                            buffer · downsample · route · drop
```

Two Docker networks let us cut the backhaul (`edge-net` keeps the devices
talking to the edge while `backhaul-net` is severed) and prove the edge
buffers and recovers. The upstream Collector stands in for a regional or
cloud Collector and is the only hop that authenticates to Scout.

## What the edge Collector does

1. **Disk-buffered queue** - `file_storage` extension backing the
   exporter `sending_queue`. Batches not yet acked by the upstream live on
   disk and survive a restart or an outage.
2. **Downsampling** - the `interval` processor collapses a 30s window of
   gauge readings to one datapoint, cutting bandwidth on high-frequency
   sensors.
3. **Priority routing** - a `routing` connector sends `fleet.priority=high`
   straight through at full resolution; everything else takes the
   downsampling path.
4. **Battery-aware drop** - a `filter` processor drops metrics when
   `device.battery.level < 20` and `fleet.priority != critical`, to extend
   the life of devices that are not worth waking for routine telemetry.

## Run it

The upstream Collector authenticates to Scout with the OAuth2
client-credentials extension. Provide the four `SCOUT_*` values either by
sourcing your Scout config or by copying `.env.example` to `.env`.

```bash
# Source your Scout config, then boot (re-source it for every compose
# command - the file uses :? guards that compose re-evaluates each time).
set -a && . ~/.config/base14/scout-otel-config.env && set +a
docker compose up --build -d
```

Everything is online within ~30s. Tear down with `docker compose down -v`
(the `-v` clears the disk queue volume).

## Outage test: zero data loss

```bash
scripts/simulate-outage.sh        # 60s outage by default
```

The script disconnects the upstream from `backhaul-net`, watches the edge
queue grow while producers keep publishing, reconnects, and confirms the
queue drains back to zero. The buffered readings arrive in Scout with their
original timestamps - OTLP carries the event time, so late delivery does not
distort the series.

To prove the queue is genuinely on disk, restart the edge Collector while
the backhaul is down: the queue depth is unchanged after the restart because
it was reloaded from the `file_storage` volume.

## Battery test: selective drop

```bash
scripts/simulate-low-battery.sh
```

This restarts `sensor-001` reporting `device.battery.level=15` and launches a
second device `sensor-critical` on the same low battery but
`fleet.priority=critical`. In Scout, `iot.sensor.temperature` for
`sensor-001` stops arriving (dropped at the edge) while `sensor-critical`
keeps reporting. Both devices' traces flow regardless - the filter is
metrics-only.

## Tuning

- **Downsampling window** - `interval: 30s` in
  `edge-collector/config.yaml`. The `interval` processor emits the last
  value seen per window for gauges; shorten it for finer resolution, lengthen
  it to save more bandwidth.
- **Full-rate fleets** - add resource attributes to the `routing` connector
  table to carve out more priorities; the default route is the downsampler.
- **Queue budget** - `sending_queue.queue_size` (in batches) bounds the disk
  queue. Size it for your worst-case outage at your batch rate. When the queue
  is full, new batches are dropped (the older, already-queued data is kept).

## Caveats

- **Disk full** - `file_storage` is bounded by `queue_size`, not by a byte
  cap. On a constrained gateway, set `queue_size` so the worst case fits the
  partition, and monitor `otelcol_exporter_queue_size`.
- **Clock skew on reconnect** - replayed data keeps its original OTLP
  timestamp, so reconnect "just works" as long as device clocks are roughly
  correct (NTP or a periodic sync). A device whose clock is hours off will
  land its late data in the wrong window.
- **Device-to-edge gap** - this pattern buffers the edge-to-backhaul link.
  While the edge Collector itself restarts, devices briefly cannot reach it;
  device-side buffering is a separate concern.
- **Demo simplifications** - the edge Collector runs as root so the named
  queue volume is writable regardless of host UID, and there is no TLS
  between edge and upstream. Both belong in a production hardening pass.

## Documentation

Full write-up:
[docs.base14.io/instrument/iot/edge-collector-patterns](https://docs.base14.io/instrument/iot/edge-collector-patterns/).
