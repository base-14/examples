# SQL Server Telemetry

Runnable example that monitors a Microsoft SQL Server 2022 instance with the
OpenTelemetry Collector's `sqlserverreceiver` and ships OTLP to base14 Scout
or any upstream collector.

A SQL Server 2022 container, a one-shot init container that creates the
read-only `otel_monitor` login, and the collector boot together with one
command.

## Architecture

```text
  sqlserver (mcr.microsoft.com/mssql/server:2022-latest, linux/amd64)
       |   port 1433, sa password from $MSSQL_SA_PASSWORD
       |
  init-monitor-user (one-shot, reuses the sqlserver image)
       |   creates login [otel_monitor] + grants:
       |     VIEW SERVER PERFORMANCE STATE
       |     VIEW ANY DATABASE
       |
  otel-collector (otel/opentelemetry-collector-contrib:0.151.0)
       |   sqlserverreceiver -> processors[batch, resource]
       |   -> exporters[otlphttp/b14, debug]
       v
   base14 Scout (or any OTLP/HTTP endpoint)
```

## Prerequisites

- Docker Desktop / Docker Engine with Compose v2.
- On Apple Silicon: Docker Desktop with Rosetta or QEMU emulation enabled
  (the SQL Server 2022 image is `linux/amd64` only). First cold pull +
  startup is typically 2-3 minutes; warm starts are under 60 seconds.
- A base14 Scout tenant URL if you want to forward metrics. The example
  works without one - the `debug` exporter prints metrics to the
  collector's stdout regardless.

## Quick start

```bash
cd components/sqlserver-telemetry
cp .env.example .env       # edit MSSQL_SA_PASSWORD, SQLSERVER_PASSWORD, OTEL_EXPORTER_OTLP_ENDPOINT
docker compose up -d
docker compose ps          # wait for sqlserver to be healthy and init-monitor-user to exit 0
docker compose logs -f otel-collector
```

You'll see the first scrape of metrics within 10-30 seconds (the
collector's `collection_interval` is 10s; first scrape is gated on the
`sqlserver` container being healthy, which takes ~30s on first start).

Stop with `docker compose down` (add `-v` to also drop the SQL Server
data volume).

## What you'll see

The receiver collects 37 metrics on Linux containers across these
categories. (50 metrics on Windows hosts; 13 of the default-enabled
metrics are Windows-perfcounter-only and silently skip on Linux.)

| Category | Metrics emitted on Linux |
| --- | --- |
| Throughput | `sqlserver.batch.request.rate`, `sqlserver.batch.sql_compilation.rate`, `sqlserver.batch.sql_recompilation.rate` |
| Locks & deadlocks | `sqlserver.lock.wait.rate`, `sqlserver.lock.wait.count`, `sqlserver.lock.timeout.rate`, `sqlserver.deadlock.rate`, `sqlserver.processes.blocked` |
| Buffer cache & memory | `sqlserver.page.buffer_cache.hit_ratio`, `sqlserver.page.buffer_cache.free_list.stalls.rate`, `sqlserver.page.life_expectancy`, `sqlserver.page.lookup.rate`, `sqlserver.memory.usage`, `sqlserver.memory.grants.pending.count` |
| Per-database I/O | `sqlserver.database.io`, `sqlserver.database.latency`, `sqlserver.database.operations`, `sqlserver.database.full_scan.rate`, `sqlserver.database.execution.errors`, `sqlserver.database.tempdb.space`, `sqlserver.database.tempdb.version_store.size` |
| Connections & sessions | `sqlserver.user.connection.count`, `sqlserver.login.rate`, `sqlserver.logout.rate` |
| Host & resource | `sqlserver.computer.uptime`, `sqlserver.cpu.count`, `sqlserver.os.wait.duration`, `sqlserver.resource_pool.disk.operations`, `sqlserver.resource_pool.disk.throttled.read.rate`, `sqlserver.resource_pool.disk.throttled.write.rate`, `sqlserver.table.count`, `sqlserver.database.count`, `sqlserver.database.backup_or_restore.rate`, `sqlserver.index.search.rate`, `sqlserver.transaction.delay`, `sqlserver.transaction.mirror_write.rate`, `sqlserver.replica.data.rate` |

## Forwarding to Scout (or another upstream)

The collector ships metrics to `${OTEL_EXPORTER_OTLP_ENDPOINT}` via the
`otlphttp/b14` exporter, in addition to the local `debug` exporter. To
disable local stdout output once you've verified flow, drop `debug`
from the `metrics` pipeline in `otel-collector-config.yaml`.

To forward to your own collector instead of Scout, set
`OTEL_EXPORTER_OTLP_ENDPOINT=http://your-collector:4318` in `.env`.

## Verify the monitoring user

```bash
docker compose exec sqlserver /opt/mssql-tools18/bin/sqlcmd \
  -S localhost -U sa -P "$MSSQL_SA_PASSWORD" -C \
  -Q "SELECT name, type_desc FROM sys.server_principals WHERE name = N'otel_monitor';"
```

Expected output: one row, `otel_monitor` with `type_desc = SQL_LOGIN`.

## Troubleshooting

### `docker compose up` hangs at `sqlserver` health-check

First-cold-start of SQL Server 2022 under x86 emulation on Apple
Silicon takes 30-60 seconds. The healthcheck has a 60s `start_period`
and 12 retries at 10s each, so it tolerates a 2-minute warm-up. If it
still fails, check `docker compose logs sqlserver` for SA password
policy violations (8+ chars, mixed case, digit, symbol).

### `init-monitor-user` exits non-zero

Most often a transient connection failure during SQL Server warm-up.
Re-run `docker compose up -d` - the init service will retry and the
script is idempotent.

### Collector logs show `Login failed for user 'otel_monitor'`

The `init-monitor-user` step did not complete successfully. Check
`docker compose logs init-monitor-user` for SQL errors. Verify
`SQLSERVER_PASSWORD` in `.env` matches what the init script was given.

### No metrics in Scout

Check the collector's `debug` output first - if metrics print to stdout
but don't reach Scout, the issue is the `otlphttp/b14` exporter.
Confirm `OTEL_EXPORTER_OTLP_ENDPOINT` is set to your tenant URL and
that the collector can reach it. The `tls.insecure_skip_verify: true`
flag should be removed in production.

### Many default metrics are not appearing

13 of the receiver's 20 default-enabled metrics use Windows performance
counters and never emit on Linux. The "What you'll see" table above
lists what's actually available on Linux containers. Run on a Windows
SQL Server host for the full set.
