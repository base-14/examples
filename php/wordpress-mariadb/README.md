# WordPress + MariaDB OpenTelemetry

A runnable OpenTelemetry example for stock WordPress on MariaDB, instrumented
with `opentelemetry-auto-wordpress` and `opentelemetry-auto-mysqli`. Nothing is
installed into WordPress and no theme is modified. The PECL extension attaches
through `auto_prepend_file`, so the traces come from WordPress core and the
`mysqli` driver it uses to reach MariaDB.

Two deployment profiles are included, Apache + mod_php (default) and PHP-FPM +
nginx (`--profile fpm`). Both produce the same spans.

## Prerequisites

- Docker and Docker Compose.
- `curl` on the host, used by `scripts/test-api.sh` and
  `scripts/verify-scout.sh`.
- A base14 Scout account, optional. Without real credentials telemetry still
  flows to the collector's local `file/capture` and `debug` exporters, which
  covers everything here except the final Scout check.

## Quick start

```bash
git clone https://github.com/base-14/examples.git
cd examples/php/wordpress-mariadb
cp .env.example .env   # edit in your Scout credentials, or leave the placeholders
set -a && source .env && set +a
docker compose up -d --build
```

`wp-init` seeds three posts in an `observability` category, an `about` page,
and one approved comment, then exits. Wait for it:

```bash
docker compose logs -f wp-init
```

Once it prints `Seed complete`, drive the path set:

```bash
./scripts/test-api.sh
```

Expect `Passed: 8  Failed: 0`. The site is at <http://localhost:8080>, or
`$WP_APACHE_PORT`.

To watch spans arrive, tail the collector while running the path set from
another shell:

```bash
docker compose logs -f otel-collector | grep 'Span #'
```

## What gets traced

Each request produces a root span named after the entry script PHP ran, `GET
/index.php` for anything routed through the front controller and `GET
/wp-login.php` for a direct script hit, `WP.*` spans for the stages of
`WP::main()`, and a `mysqli_query` child under every `wpdb.query`. A single
post runs to 86 spans on this seeded site.

The [WordPress OpenTelemetry guide](https://docs.base14.io/instrument/apps/auto-instrumentation/wordpress)
has the full span model: every span name, its kind, its parent, and its
attribute keys.

## The two profiles

| | Apache + mod_php (default) | PHP-FPM + nginx (`--profile fpm`) |
| --- | --- | --- |
| Start | `docker compose up -d --build` | `docker compose --profile fpm up -d --build` |
| Port | `${WP_APACHE_PORT:-8080}` | `${WP_FPM_PORT:-8081}` |
| Web server | Apache, `mod_php` in-process | nginx in front of PHP-FPM over FastCGI |
| Database | `wordpress` | `wordpress_fpm` |
| Seed | `wp-init` | `wp-init-fpm` |

Both run side by side against the same `mariadb` container but use separate
databases, so running both at once does not mix content:

```bash
docker compose --profile fpm up -d --build
docker compose logs -f wp-init-fpm   # wait for "Seed complete"
SITE_URL=http://localhost:${WP_FPM_PORT:-8081} ./scripts/test-api.sh
```

Set `SITE_URL` explicitly for the FPM profile. It defaults to the Apache port,
so leaving it out re-tests Apache instead.

## Environment variables

In `.env.example`. Copy to `.env` and load it into the shell before
`docker compose up` with `set -a && source .env && set +a`:

| Variable | Purpose | Default |
| --- | --- | --- |
| `SCOUT_ENDPOINT` | Scout OTLP HTTP endpoint | placeholder, collector starts but export fails |
| `SCOUT_CLIENT_ID` | Scout OAuth2 client ID | placeholder |
| `SCOUT_CLIENT_SECRET` | Scout OAuth2 client secret | placeholder |
| `SCOUT_TOKEN_URL` | Scout OAuth2 token endpoint | placeholder |
| `WP_APACHE_PORT` | Host port for the Apache profile | `8080` |
| `WP_FPM_PORT` | Host port for the FPM profile (nginx) | `8081` |
| `COLLECTOR_METRICS_PORT` | Host port for the collector's metrics endpoint | `8888` |

`WP_VERSION` (default `7.0.4`) is not in `.env.example`. Set it in the shell to
build a different WordPress image tag.

Compose takes `${SCOUT_ENDPOINT}` and the rest from the shell environment
first, and falls back to `.env` only for names the shell does not export. If a
`SCOUT_*` variable is already exported, editing `.env` will not change where
telemetry goes. Either `unset` the four `SCOUT_*` variables first, or start the
stack with `env -i "$(command -v docker)" compose up -d`. `.env` still has to
exist so that unexported names resolve. `scripts/verify-scout.sh` prints the
`SCOUT_ENDPOINT` the running collector was actually started with.

## The path set

`scripts/test-api.sh` drives eight fixed paths against `$SITE_URL`. The span
counts in the guide are written against this set, so changing it invalidates
them:

| Path | Expected | Exercises |
| --- | --- | --- |
| `/` | 200 | Home, main query |
| `/first-post/` | 200 | Single post, pretty permalink |
| `/about/` | 200 | Page |
| `/category/observability/` | 200 | Archive, 3 seeded posts |
| `/?s=scout` | 200 | Search |
| `/wp-json/wp/v2/posts` | 200 | REST API |
| `/wp-login.php` | 200 | Direct script hit, not routed through `WP::main()` |
| `/this-path-does-not-exist/` | 404 | Error path |

## Verifying Scout

`scripts/verify-scout.sh` drives the path set and reads the collector's
exporter metrics before and after. It needs the target to be the only WordPress
server running, so stop the other profile first:

```bash
# Apache
docker compose stop wordpress-fpm nginx
./scripts/verify-scout.sh

# PHP-FPM + nginx
docker compose stop wordpress
SITE_URL=http://localhost:${WP_FPM_PORT:-8081} ./scripts/verify-scout.sh
```

`SITE_URL` selects which profile gets verified and defaults to Apache. Bring
the other profile back with `docker compose start` when you are done.

A pass needs `otelcol_receiver_accepted_spans` and `otelcol_exporter_sent_spans`
to have both risen past a 176-span floor, with no new
`otelcol_exporter_send_failed_spans`. On failure the two counters indicate
where the problem is. `accepted_spans` below the floor means the collector
received almost nothing, which points at the target's instrumentation or
traffic. `accepted_spans` above the floor with `sent_spans` below it means the
collector has the spans but cannot ship them, so check the endpoint, the
credentials, and the network.

A pass means the collector received the spans and the OTLP endpoint accepted
them. It does not mean they are queryable, and it covers spans only, not the
metrics or logs pipelines. Confirm the rest in Scout: filter on
`service.name=wordpress-mariadb-otel` and `environment=development`, and open a
trace for `/first-post/`. It should show `wpdb.query` and `mysqli_query`
children under `GET /index.php`.

## Resetting the stack

To reset a WordPress container from its image without touching any volume:

```bash
docker compose up -d --no-deps --force-recreate wordpress
```

Use that rather than `docker compose down -v`, which also destroys
`wordpress-fpm-data` and the seeded FPM site with it.

## Troubleshooting

**Collector won't start: `extensions::oauth2client: no ClientID provided` or
`exporters::otlp_http/scout: at least one endpoint must be specified`.** There
is no `.env` file, so Compose has nothing to substitute for `${SCOUT_ENDPOINT}`
and the rest. Run `cp .env.example .env` before `docker compose up`.

**Port already in use.** Something is bound to `8080`, `8081`, or `8888`. Set
`WP_APACHE_PORT`, `WP_FPM_PORT`, or `COLLECTOR_METRICS_PORT` in `.env` and
re-run `docker compose up -d --build`. Export them into the shell you run
`verify-scout.sh` from as well, or the script keeps using the defaults.

**FPM worker can't see `OTEL_*` or the DB variables (`clear_env`).** Check what
your pool already sets before changing anything. The official `wordpress:*-fpm`
image ships `docker.conf` with `clear_env = no` active:

```bash
docker compose exec wordpress-fpm cat /usr/local/etc/php-fpm.d/docker.conf
```

Where a pool does set `clear_env = yes`, it strips `WORDPRESS_DB_*` along with
the `OTEL_*` variables, so WordPress returns an HTTP 500 with "Error
establishing a database connection" before you notice the missing telemetry.
Test through an actual FPM worker, not the CLI SAPI, which `clear_env` does not
govern.

**No spans in the collector's debug log.** Confirm the `wordpress` or
`wordpress-fpm` container is healthy with `docker compose ps`, then run
`docker compose logs -f otel-collector` while driving `./scripts/test-api.sh`
from another shell. `Span #` blocks should appear within a few seconds of each
request. If they do not, check the extension and the prepend inside the
container:

```bash
docker compose exec wordpress php -m | grep opentelemetry
docker compose exec wordpress php -i | grep auto_prepend_file
```

**`verify-scout.sh` reports a counter below the floor with real credentials
set.** Read its `[8/8]` verdict first, which indicates where to look:

- **`accepted_spans` under the floor.** The problem is on the WordPress side
  rather than in the export path. Confirm requests succeed
  (`SITE_URL=<that url> ./scripts/test-api.sh`) and that instrumentation is
  loaded there. If `sent_spans` moved anyway, that is an older backlog
  draining rather than this run's traffic.
- **`accepted_spans` cleared the floor, `sent_spans` did not.** The collector
  has the spans but cannot ship them. Check
  `docker compose logs otel-collector | grep -i scout` for the HTTP or auth
  error, confirm the `SCOUT_ENDPOINT` printed at `[3/8]` is the one you meant,
  and that it is reachable from inside the collector's network namespace rather
  than only from the host.
