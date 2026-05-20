# SNMP Overview

Overview per `components/DASHBOARD_SPEC.md`. Four collapsed-row zones
covering all three device classes shipped with this example
(`compute`, `network`, `power`). One dashboard beats three because the
header tile row stays informative regardless of which device kind is
in focus.

## Filters

| Variable | Label | Multi | Source | Notes |
| --- | --- | --- | --- | --- |
| `environment` | Environment | no | `SELECT DISTINCT ResourceAttributes['deployment.environment'] FROM otel_metrics_gauge WHERE TimeUnix > now() - INTERVAL 1 DAY` | OTel-standard key. Set by `resource/{linux,router,ups}` processors in `config/otel-collector.yaml`. |
| `serviceName` | Service | yes (multi+includeAll) | `SELECT DISTINCT ServiceName FROM otel_metrics_gauge WHERE ... AND MetricName IN ('system.processes.count','system.network.interfaces.count','ups.battery.capacity')` | **Deviation from spec sec 4** (which says single-value). One SNMP dashboard genuinely covers three service.name values per environment (`linux-host-01`, `cisco-router-01`, `apc-ups-01`). Multi+includeAll lets the operator land on "All" and see every device class at once; the per-zone metric filters scope panels to the right class regardless. Pinned to three cheap anchor metrics (one per device kind) to keep the dropdown bounded. |
| `device` | Device | yes (multi+includeAll) | `SELECT DISTINCT ResourceAttributes['device.id'] ...` pinned to the same three anchor metrics | Identity per spec sec 4. `device.id` is set from SNMPv2-MIB `sysName` per pipeline (receiver-emitted, not operator-set), so it is the canonical identity. In the simulator each pipeline maps 1:1 to a service.name, but `device.id` is the right key once a single pipeline scrapes multiple endpoints. |

## Surface discriminator

Spec sec 4a discusses an `Attributes['type']` filter for cloud
receivers that emit a resource-type identifier (Azure Monitor, AWS
CloudWatch). The OTel `snmpreceiver` does not set such an attribute --
each pipeline already produces a unique `service.name`, and metric
names do not overlap across the three device classes in this example
(`network.io` is router-only, `system.cpu.utilization` is linux-only,
`ups.*` is UPS-only). The combination of `serviceName` filter +
metric-name predicate per zone discriminates surfaces cleanly without
a separate `type` attribute. If a future SNMP fragment adds device
classes whose metric names *do* overlap, add `device.kind` (resource
attribute) as the discriminator and document here.

## Translation notes

- **Environment key.** Source `resource/{linux,router,ups}` processors
  set `deployment.environment` (OTel-standard). Older builds of this
  example set the bare `environment` key -- if you import this
  dashboard against a collector older than the bundled one, run
  `make replay` after restarting the collector to repopulate the new
  key, or temporarily edit the variable queries to use bare
  `environment` until the data window rolls.
- **Throughput stats use `$perSecondColumnsAggregated`.** The throughput
  tiles compute *per-interface counter rate first, then sum across
  interfaces*. A naive `$perSecond(Value)` would call `max(Value)` per
  bucket across all (device, interface) series, collapse them into a
  single pseudo-series, and return the rate of whichever interface had
  the largest counter. Spec sec 5a reaches for this exact pattern --
  do not hand-roll the lagInFrame nesting.
- **Counter resets.** `$perSecond*` macros guard against negative
  deltas (counter wrap or device reboot) and drop them. Reflected as
  occasional gaps in throughput / error timeseries; expected.
- **Memory % is computed in one bucket.** `(memTotal - memAvailable) /
  memTotal` is computed inside one `$timeSeries` group so the two
  metric values come from the same scrape window -- otherwise a
  half-bucket-late memTotal can race with memAvailable and produce a
  spurious negative reading.
- **Load average is x100.** UCD `laLoadInt` returns the load as an
  integer x 100. Panel queries divide by 100 to display the
  conventional decimal.
- **Runtime is centiseconds.** UPS battery runtime is reported in
  centiseconds (TimeTicks). All panel queries divide by 6000 to
  display minutes.
- **Memory is KiB.** UCD `memTotal/Avail/Cached/Buffered` are KiB. The
  Memory composition panel multiplies by 1024 to display bytes; the
  Memory used % panel keeps the values raw since the units cancel in
  the percentage.

## Conditional metrics

Three classes of metric are scoped to a single device class. Filtering
the dashboard to a single `serviceName` will leave the other two zones
empty -- this is by design.

- **Network zone** is populated only by `cisco-router-01` (or whatever
  service.name your router pipeline uses). Series for `network.io`,
  `network.errors`, `network.interface.{admin,oper}_status` come from
  IF-MIB and only the router pipeline scrapes that MIB.
- **Compute zone** is populated only by `linux-host-01`. CPU, load,
  memory, processes, sessions are HOST-RESOURCES and UCD-SNMP -- only
  the linux pipeline scrapes them.
- **Power zone** is populated only by `apc-ups-01`. Everything in
  `ups.*` is PowerNet-MIB enterprise-318 specific.

## Zones

### Overview (collapsed) -- 6 stats

Stats use `$timeFilter` so the dashboard time picker drives the stat
window per spec sec 6.

| Panel | Width | Metric | Aggregation | Unit | Thresholds |
| --- | --- | --- | --- | --- | --- |
| Devices reporting | 4 | anchor metrics | `uniqExact(ServiceName)` | `short` | green |
| Receive throughput | 4 | `network.io` direction=receive | `$perSecondColumnsAggregated` rolled up to `'total'` | `Bps` | green |
| Transmit throughput | 4 | `network.io` direction=transmit | `$perSecondColumnsAggregated` rolled up to `'total'` | `Bps` | green |
| Interfaces down | 4 | `network.interface.oper_status` | `count(...) WHERE last_oper = 2` over a per-interface argMax subquery | `short` | green, red >= 1 |
| UPS on battery | 4 | `ups.output.status` | `max(if(Value=3,1,0))`, reduce `max` | `short` | green, red >= 1, mappings 0=OK / 1=On battery |
| Shortest UPS runtime | 4 | `ups.battery.runtime_remaining` | `min(Value)/6000` | `m` (minutes) | red, amber >= 10, green >= 30 |

### Network (collapsed) -- 6 panels

| Panel | Width | Metric | Macro | Unit |
| --- | --- | --- | --- | --- |
| Receive throughput by interface | 12 | `network.io` direction=receive | `$perSecondColumns(<device>\|<iface>, Value)` | `Bps`, stacked |
| Transmit throughput by interface | 12 | `network.io` direction=transmit | same with direction=transmit | `Bps`, stacked |
| Errors / sec by interface | 24 | `network.errors` | `$perSecondColumns` x 2 targets, suffix `\|rx` / `\|tx` on the iface key | `ops` |
| Admin status by interface | 12 | `network.interface.admin_status` | `$columns(<iface>, anyLast(Value))` | state-timeline, mapped 1=up / 2=down / 3=testing |
| Operational status by interface | 12 | `network.interface.oper_status` | same with oper_status | state-timeline, mapped 1-5 |
| Interface count by device | 24 | `system.network.interfaces.count` | `$columns(device, anyLast(Value))` | `short` |

### Compute (collapsed) -- 6 panels

| Panel | Width | Metric | Macro | Unit |
| --- | --- | --- | --- | --- |
| CPU utilization per core | 12 | `system.cpu.utilization` | `$columns(<device>\|<cpu.index>, anyLast(Value))` | `percent` |
| Load average (1m / 5m / 15m) | 12 | `system.cpu.load_average.{1m,5m,15m}` | `$columns(<device>\|1m, anyLast(Value)/100)` x 3 targets | `short` |
| Memory used (%) | 12 | `system.memory.{total,available}` | `(total - avail) / total * 100` per bucket per device | `percent` |
| Memory composition | 12 | `system.memory.{cached,buffered,available}` | `$columns(<device>\|cached, max(Value)*1024)` x 3 targets | `bytes`, stacked |
| Process count by device | 12 | `system.processes.count` | `$columns(device, anyLast(Value))` | `short` |
| User sessions by device | 12 | `system.users.count` | `$columns(device, anyLast(Value))` | `short` |

### Power (collapsed) -- 8 panels

| Panel | Width | Metric | Macro | Unit |
| --- | --- | --- | --- | --- |
| Battery capacity (%) | 8 | `ups.battery.capacity` | `$columns(device, anyLast(Value))` | `percent` |
| Runtime remaining (min) | 8 | `ups.battery.runtime_remaining` | `$columns(device, anyLast(Value)/6000)` | `m` |
| Output load (%) | 8 | `ups.output.load` | `$columns(device, anyLast(Value))` | `percent` |
| Battery status | 12 | `ups.battery.status` | `$columns(device, anyLast(Value))` | state-timeline, mapped 1-4 |
| Output status | 12 | `ups.output.status` | `$columns(device, anyLast(Value))` | state-timeline, mapped 1-6 |
| Input voltage / frequency | 12 | `ups.input.{voltage,frequency}` | `$columns(<device>\|V, anyLast)` x 2 | `short` |
| Battery temperature | 12 | `ups.battery.temperature` | `$columns(device, anyLast(Value))` | `celsius` |
| Output voltage / current | 24 | `ups.output.{voltage,current}` | `$columns(<device>\|V, anyLast)` x 2 | `short` |

## Alert recipes

Wire these in your alerting system, not on the dashboard. Severities
assume 2-minute evaluation windows.

| # | Condition | Severity | Notes |
| --- | --- | --- | --- |
| 1 | `ups.output.status == 3` for 1m | Critical | UPS on battery |
| 2 | `ups.battery.runtime_remaining / 6000 < 10` | Critical | Less than 10 min runtime |
| 3 | `ups.battery.capacity < 15` | Critical | Capacity low |
| 4 | `ups.battery.capacity < 30` | Warning | Capacity degrading |
| 4b | `ups.battery.replace_indicator == 2` | Warning | Battery flagged for replacement |
| 5 | `ups.output.load > 90` | Critical | Overload risk |
| 6 | `ups.battery.temperature > 50` | Critical | Thermal risk |
| 7 | `network.interface.oper_status != 1 AND network.interface.admin_status == 1` | Critical | Unexpected down |
| 8 | `rate(network.errors[5m]) > 1` | Warning | Per interface |
| 9 | Throughput / link speed > 90% for 5m | Warning | Per interface, requires JOIN with `network.interface.speed` |
| 10 | `system.cpu.load_average.1m / 100 > cpu_count * 1.5` | Warning | Needs cpu_count from `system.cpu.utilization` series |
| 11 | `(1 - system.memory.available / system.memory.total) > 0.9` | Warning | Memory pressure |
| 12 | Device silent for 3 x `collection_interval` | Critical | Device went away (`time() - max(TimeUnix) > 90s` against a 30s collection_interval) |

## Out of scope

- **Link utilization gauge.** Computing `rate / (interface.speed *
  1e6) * 100` requires joining a counter (`network.io`) with a gauge
  (`network.interface.speed`) on (device, interface) at bucket
  granularity. Doable but ugly in ClickHouse without a per-interface
  speed lookup table. Wire as a metric-math panel in v2 if needed.
- **Battery replace indicator.** Emitted as `ups.battery.replace_indicator`
  but easy to surface with a single-cell state panel; defer to v2.
- **Correlation strip.** A 4-panel shared-timeline row at the bottom
  (UPS state band, network errors, avg CPU, mem available) is in the
  original DASHBOARD.md draft. Add as a fifth collapsed row in v2 once
  operators express demand -- the four zones already let an operator
  expand any pair side-by-side.
- **`cpu.index` cosmetic prefix.** The receiver emits `cpu_.196608` for
  the index because `indexed_value_prefix` literally prepends to
  `.<idx>`. Cosmetic only. A `transform` processor that strips
  `cpu_.` from the label would clean up the legend; not blocking.
- **Site / region filtering.** `site.id` is emitted but not exposed as
  a filter variable in this dashboard. Add when a second site comes
  online and the operator needs the cut.

## Conventions reminder

- `schemaVersion: 42`, Grafana 12.2.
- All four rows `collapsed: true` per spec sec 7 (3+ zones).
- Pinned datasource: `{type: vertamedia-clickhouse-datasource, uid: ds-scout-altinity-ch}`.
- `database: "{{.Tenant}}"` on every target; Scout's installer
  substitutes at deploy time.
- Every target sets `useWindowFuncForMacros: true` (correctness, not
  cosmetics -- without it counter macros expand to `runningDifference`
  which returns wrong results under parallel query execution).
- Every panel sets `transparent: true`.
- `refresh: null`, `time: { from: now-1h, to: now }`.
- All variables use `${var:singlequote}`; all variables `refresh: 2`.
- Variable lookback is `INTERVAL 1 DAY` (spec sec 4 -- never `$timeFilter`,
  dropdowns must not empty when the operator shortens the time picker).
- No hardcoded `ServiceName = '...'` in panels.
- No `rawQuery` / `formattedQuery` keys.
