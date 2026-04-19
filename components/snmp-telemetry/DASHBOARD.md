# SNMP Operator Dashboard — Spec

A ready-to-import Scout / ClickHouse build of this spec lives at
`grafana/dashboard.json` (uses the Vertamedia ClickHouse datasource
and the `{{.Tenant}}` template). The spec below stays as the source
of truth for layout and thresholds; the JSON is one translation.

A panel-level specification for a single dashboard covering all
three device classes shipped with this example (`compute`,
`network`, `power`). One dashboard beats three because the header
stays informative regardless of which device kind is in focus.

All queries use PromQL-style shapes against the metrics this
example emits. Replace with the query language your visualizer
uses; structure and thresholds stay the same.

Two translation notes when pointing these queries at a real
backend:

- **Unit suffixes.** Some OTel→Prometheus bridges append the unit
  to gauge names (`system.memory.total` with unit `KiBy` becomes
  `system_memory_total_kibibytes`). The queries below use the
  bare name; add the suffix if your bridge emits it.
- **Resource vs. metric labels.** `service.name`, `site.id`,
  `device.kind`, `network.interface.name`, and `cpu.index` are
  resource attributes, not sample labels. In the Prometheus
  bridge they land on `target_info` and need
  `on()+group_left` joins to use as query labels. In Scout /
  ClickHouse read them from `ResourceAttributes['key']` directly.

## Dashboard variables

| Variable | Source | Default |
| --- | --- | --- |
| `site` | `site.id` label | `*` |
| `device_kind` | `device.kind` label | `*` (All) |
| `device` | `service.name` label | `*` |

All panels are filtered by the three variables above. Repeating
panels use `service.name` as the repeat dimension.

## Layout

```text
┌─────────────────────────── Incident Header ─────────────────────────┐
│  [Devices up]  [Σ in]  [Σ out]  [Ifaces down]  [UPS on batt]  [min runtime] │
├──────────────────────────────────────────────────────────────────────┤
│                          Zone 1 — Network                           │
│  [Throughput area]  [Top-N table]  [Error heatmap]                 │
│  [Status grid]      [Link util gauges]  [iface count]              │
├──────────────────────────────────────────────────────────────────────┤
│                          Zone 2 — Compute                           │
│  [CPU per core]  [Load avg]  [Mem used %]  [Mem composition]       │
│  [Process count]  [User sessions]                                   │
├──────────────────────────────────────────────────────────────────────┤
│                          Zone 3 — Power                             │
│  [Battery % ]  [Runtime mins]  [Output load]  [Batt status]         │
│  [Output status]  [In V/Hz]   [Batt temp]  [Out V/A]               │
├──────────────────────────────────────────────────────────────────────┤
│                     Zone 4 — Correlation Strip                      │
│  (shared timeline: UPS state + iface errors + CPU + mem)           │
└──────────────────────────────────────────────────────────────────────┘
```

## Incident Header — one row, six tiles

Purpose: spot trouble in three seconds without scrolling.

| # | Title | Type | Query | Thresholds |
| --- | --- | --- | --- | --- |
| 1 | Devices reporting | Stat | `count(count by (service_name) (last_over_time(system_processes_count[2m]))) + count(count by (service_name) (last_over_time(system_network_interfaces_count[2m]))) + count(count by (service_name) (last_over_time(ups_battery_capacity[2m])))` | Red if `< expected` |
| 2 | Total throughput in | Stat + sparkline | `sum(rate(network_io_bytes_total{direction="receive"}[1m]))` unit `B/s` | — |
| 3 | Total throughput out | Stat + sparkline | `sum(rate(network_io_bytes_total{direction="transmit"}[1m]))` unit `B/s` | — |
| 4 | Interfaces down | Stat | `count(network_interface_oper_status != 1 and network_interface_admin_status == 1)` | Red if `> 0` |
| 5 | UPS on battery? | Traffic-light | `max(ups_output_status == 3)` | Red if `== 1` |
| 6 | Shortest UPS runtime | Stat (minutes) | `min(ups_battery_runtime_remaining) / 6000` | `<10` red, `<30` amber |

Tile 1 picks a stable per-class gauge instead of `{__name__=~".+"}` to
avoid scanning every series on each refresh. Tile 4 excludes admin-
down interfaces so planned shutdowns don't page on-call.

## Zone 1 — Network (`device.kind="network"`)

| Panel | Type | Query | Notes |
| --- | --- | --- | --- |
| Per-interface throughput | Stacked area | `rate(network_io_bytes_total[1m])` by `network.interface.name, direction` | Two stacks per interface |
| Top N interfaces by throughput | Table | Same, ranked descending | N = 10 |
| Interface error rate | Heatmap | `rate(network_errors_total[5m])` × `service.name, network.interface.name, direction` | Split RX / TX; stops at 1/s and 10/s |
| Admin / Oper status grid | State timeline | `network_interface_admin_status`, `network_interface_oper_status` | Green = 1, Red = 2, Amber = 3/4/5 |
| Link utilization % | Gauge (per interface) | `rate(network_io_bytes_total[1m]) * 8 / (network_interface_speed * 1e6) * 100` | Warn 70, Crit 90 |
| Interface count | Stat | `system_network_interfaces_count` | Per device |

## Zone 2 — Compute (`device.kind="compute"`)

| Panel | Type | Query | Notes |
| --- | --- | --- | --- |
| CPU utilization per core | Gauge cluster | `system_cpu_utilization` by `cpu.index` | Warn 80, Crit 95 |
| Load average (1/5/15m) | Time series, 3 lines | `system_cpu_load_average_1m / 100` and 5m, 15m | Divide by 100 — raw value is × 100 |
| Memory used (%) | Stat | `(system_memory_total - system_memory_available) / system_memory_total * 100` | Warn 85, Crit 95 |
| Memory composition | Stacked area | `system_memory_{cached,buffered,available}` | Good for spotting leaks |
| Process count | Time series | `system_processes_count` | Trend, not threshold |
| User sessions | Stat | `system_users_count` | Jump-box indicator |

## Zone 3 — Power (`device.kind="power"`)

| Panel | Type | Query | Thresholds |
| --- | --- | --- | --- |
| Battery capacity | Big gauge 0–100 | `ups_battery_capacity` | Crit <15, Warn <30 |
| Runtime remaining | Big stat | `ups_battery_runtime_remaining / 6000` (minutes) | Crit <10, Warn <30 |
| Output load | Gauge | `ups_output_load` | Warn 70, Crit 90 |
| Battery status | Status panel | `ups_battery_status` mapped | 2=green, 3=red, 4=amber, 1=grey |
| Output status | Status panel | `ups_output_status` mapped | 2=green, 3=red, 4/5=amber |
| Input voltage | Time series | `ups_input_voltage` | Band ±10% of nominal |
| Input frequency | Time series | `ups_input_frequency` | Band ±1 Hz of nominal |
| Battery temperature | Time series | `ups_battery_temperature` | Warn >40, Crit >50 |
| Output voltage / current | Dual time series | `ups_output_voltage`, `ups_output_current` | Flatlines are healthy |
| Battery replace needed | Status panel | `ups_battery_replace_indicator` | 1=green (ok), 2=red (replace) |

## Zone 4 — Correlation strip

One shared timeline, no per-panel headers. Helps answer
"did the interface errors start when the UPS switched to battery?"

Stacked in one row, same time range:

1. UPS output status as a colour band (`ups_output_status`)
2. Interface error rate line (`sum(rate(network_errors_total[1m]))`)
3. Aggregate CPU line (`avg(system_cpu_utilization)`)
4. Memory availability line (`avg(system_memory_available)`)

## Starter alert recipes

Ship these alongside the dashboard. All severities assume 2-minute
evaluation windows.

| # | Condition | Severity | Notes |
| --- | --- | --- | --- |
| 1 | `ups_output_status == 3` for 1m | Critical | UPS on battery |
| 2 | `ups_battery_runtime_remaining < 600000` | Critical | Less than 10 min |
| 3 | `ups_battery_capacity < 15` | Critical | Capacity low |
| 4 | `ups_battery_capacity < 30` | Warning | Capacity degrading |
| 4b | `ups_battery_replace_indicator == 2` | Warning | Battery flagged for replacement |
| 5 | `ups_output_load > 90` | Critical | Overload risk |
| 6 | `ups_battery_temperature > 50` | Critical | Thermal risk |
| 7 | `network_interface_oper_status != 1 AND network_interface_admin_status == 1` | Critical | Unexpected down |
| 8 | `rate(network_errors_total[5m]) > 1` | Warning | Per interface |
| 9 | Link util > 90 for 5m | Warning | Per interface |
| 10 | `system_cpu_load_average_1m / 100 > cpu_count * 1.5` | Warning | Needs cpu_count label |
| 11 | `(1 - system_memory_available / system_memory_total) > 0.9` | Warning | Memory pressure |
| 12 | Device silent for 3 × `collection_interval` | Critical | Device went away |

## Build tips

- **Single dashboard, filtered by variables** — less to maintain
  than three role-specific dashboards; the header stays useful
  regardless of which device kind is selected.
- **Repeat rows by `service.name`** for Zones 2 and 3 — lets the
  dashboard scale as you add devices without edits.
- **State timelines over line charts** for admin/oper status — on-
  call eyes pick up colour blocks faster than 0-vs-1 lines.
- **Keep `site.id` as a dashboard variable** — when a second site
  comes online, the same dashboard works.
- **Don't put alert recipes on the dashboard itself** — configure
  them as real alerts in your alerting system. Panel thresholds in
  the table above are for visual colour-coding only.

## Open questions

- The `cpu.index` resource attribute currently emits as
  `cpu_.196608` (indexed_value_prefix literally prepends to `.<idx>`).
  Cosmetic, but if Zone 2's per-core gauge legend looks ugly, add
  a `transform` processor that strips `cpu_.` from the label before
  export.
- `device.kind=compute` captures Linux hosts but not bare-metal
  servers with IPMI. Once IPMI is added, consider renaming to
  `device.kind=host` or splitting `compute_linux` / `compute_ipmi`.
- UPS metrics use raw SNMP values — e.g. `ups_battery_runtime_remaining`
  is in centiseconds (TimeTicks). Dashboard queries divide by 6000
  to get minutes. A `transform` processor that normalizes all
  time-based metrics to seconds would remove this footgun.
