# Puma Metrics with OpenTelemetry

> 📚 [Full Documentation](https://docs.base14.io/category/app-instrumentation)

A minimal example showing how to expose Puma runtime metrics (threads, workers,
backlog, etc.) from a Ruby web server and ship them to
[base14 Scout](https://base14.io/scout) via the OpenTelemetry Collector.

> **Note**: Ruby's OpenTelemetry metrics SDK is still in development (0.x).
> This example uses the mature `yabeda-prometheus` stack and has the collector
> scrape it — a common production pattern while the OTel Ruby metrics SDK
> stabilises. See [OTel Ruby signal maturity](https://opentelemetry.io/docs/languages/ruby/).

## Pairs well with

This example is framework-agnostic. Drop it alongside any Rack/Puma app:

- Rails → [rails8-sqlite](../rails8-sqlite) (see "Adapting for Rails" below)
- Sinatra, Hanami, Roda, or a plain Rack app — the Puma config is identical

## How it works

```text
Puma (control app) → yabeda-puma-plugin (collect)
                       │
                       ▼
             yabeda-prometheus (expose /metrics)
                       │
                       ▼
          OTel Collector (scrape + OTLP export)
                       │
                       ▼
                 base14 Scout
```

1. `activate_control_app` enables Puma's internal stats plugin API.
2. `yabeda-puma-plugin` reads thread/worker/backlog stats and registers them
   as Yabeda metrics.
3. `yabeda-prometheus` serves those metrics as Rack middleware at `/metrics`
   on the same port as your app.
4. The OTel Collector scrapes `/metrics` via its Prometheus receiver and
   forwards to Scout using OAuth2 client credentials.

## Gems

| Gem | Purpose |
|-----|---------|
| `yabeda` | Metrics framework for Ruby |
| `yabeda-puma-plugin` | Collects Puma runtime stats |
| `yabeda-prometheus` | Exposes collected metrics as a Prometheus `/metrics` endpoint |

All three are required: `yabeda-puma-plugin` collects but doesn't expose,
`yabeda-prometheus` exposes but doesn't know about Puma, `yabeda` ties them
together.

## Metrics exposed

| Metric | Description |
|--------|-------------|
| `puma_workers` | Number of configured workers |
| `puma_booted_workers` | Number of booted workers |
| `puma_old_workers` | Number of old workers (during phased restart) |
| `puma_running` | Running worker threads (per worker) |
| `puma_busy_threads` | Currently busy threads (per worker) |
| `puma_backlog` | Established but unaccepted connections (per worker) |
| `puma_pool_capacity` | Allocatable worker threads (per worker) |
| `puma_max_threads` | Maximum threads per worker |
| `puma_requests_count` | Requests served since worker started (per worker) |

In cluster mode, per-worker metrics carry an `index` label.

## Prerequisites

- Docker Desktop or Docker Engine with Compose
- base14 Scout OIDC credentials
  ([setup guide](https://docs.base14.io/category/opentelemetry-collector-setup))
- Ruby 3.3+ (only for running locally without Docker)

## Quick start

### 1. Configure Scout credentials

```bash
cp .env.example .env
```

Then edit `.env` and fill in your Scout values:

```bash
SCOUT_ENDPOINT=https://<your-tenant>.base14.io:4318
SCOUT_CLIENT_ID=<your-client-id>
SCOUT_CLIENT_SECRET=<your-client-secret>
SCOUT_TOKEN_URL=https://<your-tenant>.base14.io/oauth/token
SCOUT_ENVIRONMENT=development
```

> These are read by the OTel Collector, not by the Puma app — the Ruby
> process never sees Scout credentials.

### 2. Start the stack

```bash
docker compose up --build
```

### 3. Generate traffic

```bash
curl localhost:3000            # hit the app a few times
curl localhost:3000/metrics    # inspect the Prometheus metrics being scraped
```

## What you'll see in Scout

After a minute of traffic, open Scout and look for metrics under service
`puma-metrics`:

- `puma_busy_threads` and `puma_pool_capacity` — thread pool pressure
- `puma_backlog` — unaccepted connections (a non-zero value means your
  thread pool is saturated)
- `puma_requests_count` — throughput per worker (rate this in Scout)
- `puma_booted_workers` vs `puma_workers` — detect failed worker boots

The collector also prints the scraped metrics to stdout via the `debug`
exporter — useful while setting up:

```bash
docker compose logs -f otel-collector
```

## Configuration

### Environment variables

| Variable | Required | Description |
| -------- | -------- | ----------- |
| `SCOUT_ENDPOINT` | Yes | base14 Scout OTLP/HTTP endpoint |
| `SCOUT_CLIENT_ID` | Yes | Scout OAuth client ID |
| `SCOUT_CLIENT_SECRET` | Yes | Scout OAuth client secret |
| `SCOUT_TOKEN_URL` | Yes | Scout OAuth token endpoint |
| `SCOUT_ENVIRONMENT` | No | Value for `deployment.environment` (default: `development`) |

These are consumed by the collector, not the app — the Ruby process never
touches Scout credentials.

## Adapting for your app

### 1. Add gems to your Gemfile

```ruby
gem "yabeda"
gem "yabeda-puma-plugin"
gem "yabeda-prometheus"
```

### 2. Configure Puma (`config/puma.rb`)

```ruby
require "yabeda"
require "yabeda/puma/plugin"

# Required — without this, yabeda-puma-plugin has no stats source
# and Puma will fail to boot.
activate_control_app

plugin :yabeda

# Non-Rails apps only — Rails calls this automatically via the yabeda railtie.
before_fork do
  Yabeda.configure!
end
```

### 3. Expose the `/metrics` endpoint

**Rack / Sinatra / Hanami** — in `config.ru`:

```ruby
require "yabeda/prometheus"
use Yabeda::Prometheus::Exporter, path: "/metrics"
```

**Rails** — in `config/application.rb` or an initializer:

```ruby
config.middleware.insert_before 0, Yabeda::Prometheus::Exporter, path: "/metrics"
```

### 4. Point the collector at your app

Use `config/otel-config.yml` from this example as-is; just change
`targets: ["puma:3000"]` to match your service's host and port.

## Troubleshooting

### Puma fails to boot with "undefined method 'plugin'" or similar

Make sure `require "yabeda/puma/plugin"` is at the **top** of
`config/puma.rb`, before `plugin :yabeda`.

### `/metrics` returns 404

The `Yabeda::Prometheus::Exporter` middleware must be mounted. For Rails,
verify it's inserted before `Rack::Sendfile` (hence `insert_before 0`).

### No metrics appearing in Scout

```bash
# Is the collector scraping?
docker compose logs otel-collector | grep "scrape"

# Is OAuth working?
docker compose logs otel-collector | grep -i "oauth\|token"

# Is the app exposing metrics?
curl -s localhost:3000/metrics | head
```

If OAuth logs show 401s, re-check `SCOUT_CLIENT_ID`, `SCOUT_CLIENT_SECRET`,
and `SCOUT_TOKEN_URL`.

### Want to scrape directly without the OTel Collector?

If you already run Prometheus, skip the collector and point your existing
scrape config at `/metrics` directly.

## Technology stack

| Component | Version |
| --------- | ------- |
| Puma | 6.x |
| Ruby | 3.3 |
| yabeda | 0.16 |
| yabeda-puma-plugin | 0.9 |
| yabeda-prometheus | 0.9 |
| OpenTelemetry Collector | 0.147.0 |

## Resources

- [yabeda](https://github.com/yabeda-rb/yabeda) — metrics framework
- [yabeda-puma-plugin](https://github.com/yabeda-rb/yabeda-puma-plugin)
- [yabeda-prometheus](https://github.com/yabeda-rb/yabeda-prometheus)
- [OTel Collector Prometheus receiver](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/receiver/prometheusreceiver)
- [base14 Scout](https://base14.io/scout)
