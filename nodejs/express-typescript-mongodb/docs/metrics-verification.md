# Metrics Verification

Export Interval: 60s | InstrumentationScope: `express-mongodb-app 1.0.0`

## Custom Application Metrics ✅

### Article Metrics

| Metric | Type | Attributes | Current Value |
| ------ | ---- | ---------- | ------------- |
| `articles.created.total` | Counter | user.id | 7 (6 users) |
| `articles.published.total` | Counter | article.id | 3 |
| `articles.deleted.total` | Counter | user.id | 1 |
| `articles.total` | Gauge | - | 6 |
| `article.content.size` | Histogram | article.id | 65 chars (avg) |
| `article.publish.duration` | Histogram | article.id | 5.67ms (avg) |

### Auth Metrics

| Metric | Type | Current Value |
| ------ | ---- | ------------- |
| `users.registered.total` | Counter | 23 |
| `users.active.total` | Gauge | 23 |
| `users.login.success.total` | Counter | 5 |
| `users.login.failed.total` | Counter | 3 |

### Job Metrics

| Metric | Type | Attributes | Current Value |
| ------ | ---- | ---------- | ------------- |
| `jobs.enqueued.total` | Counter | job.name | 3 (publishArticle) |
| `jobs.completed.total` | Counter | job.name | 3 |
| `jobs.processing.duration` | Histogram | job.name | 3-9ms range |

## Auto-Instrumentation Metrics ✅

### HTTP & Database

| Metric                        | Source                                 |
| ----------------------------- | -------------------------------------- |
| `http.server.duration`        | @opentelemetry/instrumentation-http    |
| `db.client.connections.usage` | @opentelemetry/instrumentation-mongodb |

### Node.js Runtime

| Metric                           | Description                      |
| -------------------------------- | -------------------------------- |
| `nodejs.eventloop.utilization`   | Event loop utilization (0-1)     |
| `nodejs.eventloop.time`          | Event loop tick duration         |
| `nodejs.eventloop.delay.min`     | Minimum event loop delay         |
| `nodejs.eventloop.delay.max`     | Maximum event loop delay         |
| `nodejs.eventloop.delay.mean`    | Mean event loop delay            |
| `nodejs.eventloop.delay.stddev`  | Event loop delay std deviation   |
| `nodejs.eventloop.delay.p50`     | Event loop delay p50             |
| `nodejs.eventloop.delay.p90`     | Event loop delay p90             |
| `nodejs.eventloop.delay.p99`     | Event loop delay p99             |

### V8 JavaScript Engine

| Metric                                    | Description                   |
| ----------------------------------------- | ----------------------------- |
| `v8js.gc.duration`                        | Garbage collection duration   |
| `v8js.memory.heap.limit`                  | Heap size limit               |
| `v8js.memory.heap.used`                   | Heap memory used              |
| `v8js.memory.heap.space.available_size`   | Available heap space          |
| `v8js.memory.heap.space.physical_size`    | Physical heap size            |

## Verification Commands

**View all custom metrics:**

```bash
docker logs otel-collector 2>&1 | tail -3000 | \
  grep -A 1000 "InstrumentationScope express-mongodb-app" | \
  grep "Name:" | sort -u
```

**Search specific metric:**

```bash
docker logs otel-collector 2>&1 | grep -A 15 "articles.created.total"
```

## Base14 Scout Queries

```promql
# Article creation rate
sum(rate(articles.created.total[5m]))

# Login success rate
rate(users.login.success.total[5m]) /
  (rate(users.login.success.total[5m]) + rate(users.login.failed.total[5m]))

# HTTP P95 latency
histogram_quantile(0.95, rate(http.server.duration[5m]))

# Job success rate
rate(jobs.completed.total[5m]) / rate(jobs.enqueued.total[5m])
```

## Notes

- Metrics export every 60 seconds (wait up to 1min for updates)
- Cumulative aggregation (totals since app start)
- High-cardinality attributes (user.id, article.id) create separate data points
