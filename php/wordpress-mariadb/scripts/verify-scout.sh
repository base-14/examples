#!/bin/bash
# Confirms telemetry actually reaches Scout, using the collector's own
# metrics - not a log grep. Export failures only surface as an error-level
# log line once the retry window closes
# (retry_on_failure.max_elapsed_time in config/otel-config.yaml, 300s), so a
# script that runs for a few seconds and greps the log for errors reports
# success while export is silently failing.
#
# Reads otelcol_receiver_accepted_spans, otelcol_exporter_sent_spans and
# otelcol_exporter_send_failed_spans from the collector's Prometheus metrics
# endpoint (service.telemetry.metrics in config/otel-config.yaml, published
# on the host at ${COLLECTOR_METRICS_PORT:-8888}), before and after driving
# traffic against $SITE_URL. A pass requires both accepted_spans and
# sent_spans to have risen by at least SPAN_DELTA_FLOOR, and send_failed_spans
# to have gained no new failures. A non-increasing sent_spans is a failure
# even with no error logged - that is the case a log grep misses.
#
# accepted_spans is gated as well as sent_spans because they answer different
# questions: sent_spans counts what the exporter shipped in the window, which
# includes spans queued earlier and released when a retry clears inside
# retry_on_failure.max_elapsed_time. Gating only sent_spans would let a
# backlog drain clear the floor while the target produced nothing.
#
# All three counters are collector-global: they carry no attribute tying a
# span to the server that produced it. Two guards stop a silent target from
# passing on somebody else's spans:
#   - profile isolation ([4/8]) refuses the run unless the target's
#     WordPress server is the only one up, so nothing else feeds the
#     counters during the window;
#   - SPAN_DELTA_FLOOR is derived from the fixed path set and applied to both
#     span deltas, set high enough that stray traffic cannot reach it.
#
# SITE_URL defaults to the Apache profile. Running this against the FPM
# profile requires setting SITE_URL explicitly - see "The two profiles" in
# README.md.

set -uo pipefail

APACHE_PORT="${WP_APACHE_PORT:-8080}"
FPM_PORT="${WP_FPM_PORT:-8081}"
SITE_URL="${SITE_URL:-http://localhost:${APACHE_PORT}}"
COLLECTOR_HEALTH="${COLLECTOR_HEALTH:-http://localhost:13133}"
COLLECTOR_METRICS="${COLLECTOR_METRICS:-http://localhost:${COLLECTOR_METRICS_PORT:-8888}/metrics}"
EXPORTER_ID="${SCOUT_EXPORTER_ID:-otlp_http/scout}"
RECEIVER_ID="${SCOUT_RECEIVER_ID:-otlp}"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Floor applied to BOTH span deltas - accepted_spans and sent_spans. Named for
# what it gates, not for one counter: changing it changes the pass condition on
# production and on export together.
#
# scripts/test-api.sh drives 8 fixed paths. The smallest trace any of them
# produces is /wp-login.php at 22 spans, so a run that really drove all 8
# cannot produce or export fewer than 8 x 22 = 176. The Apache healthcheck
# trace is 35 spans on a 10s interval, so stray healthcheck traffic cannot
# reach 176 inside this script's window even if the profile guard were
# bypassed. A delta of 1 must not pass.
SPAN_DELTA_FLOOR=176

# Collector batch.timeout is 5s (config/otel-config.yaml); 8s leaves headroom.
FLUSH_WAIT=8

echo "=== Scout verification ==="
echo "Target: $SITE_URL"
echo ""

echo "[1/8] Collector health"
CODE=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "$COLLECTOR_HEALTH" 2>/dev/null)
CODE="${CODE:-000}"
if [ "$CODE" = "200" ]; then
    echo "  OK"
else
    echo "  FAIL - collector not responding (HTTP $CODE) at $COLLECTOR_HEALTH"
    echo "  Check: docker compose ps   (run from $PROJECT_DIR)"
    exit 1
fi

echo ""
echo "[2/8] Collector metrics endpoint"
# Without this the whole measurement silently reads zero: an unreachable
# metrics endpoint yields no matching series, every counter reads 0, and the
# run blames the target for a number the collector was never asked for.
METRIC_LINES=$(curl -s --max-time 10 "$COLLECTOR_METRICS" 2>/dev/null | grep -c '^otelcol_')
if ! [[ "$METRIC_LINES" =~ ^[0-9]+$ ]] || [ "$METRIC_LINES" -eq 0 ]; then
    echo "  FAIL - no otelcol_* series at $COLLECTOR_METRICS"
    echo "  Every counter this script reads would come back 0 and the run would"
    echo "  blame the target for a number the collector was never asked for."
    echo "  This script read $COLLECTOR_METRICS. The collector's metrics are"
    echo "  published somewhere else, or not at all. Either COLLECTOR_METRICS_PORT"
    echo "  is set in .env but not exported into this shell, so the script fell"
    echo "  back to 8888 while Compose published another port - or it is exported"
    echo "  and does not match the port the stack was actually started with."
    echo "  Check what is published, then point the script at it:"
    echo "    docker compose ps otel-collector   (run from $PROJECT_DIR)"
    echo "    set -a && source .env && set +a && $0"
    echo "    COLLECTOR_METRICS=http://localhost:PORT/metrics $0"
    exit 1
fi
echo "  OK - $METRIC_LINES otelcol_* series at $COLLECTOR_METRICS"

echo ""
echo "[3/8] Scout credentials"
for var in SCOUT_ENDPOINT SCOUT_CLIENT_ID SCOUT_CLIENT_SECRET SCOUT_TOKEN_URL; do
    if [ -z "${!var:-}" ]; then
        echo "  WARN - $var is not set in this shell"
    else
        echo "  OK - $var is set"
    fi
done
echo "  Precedence: Compose resolves compose.yaml's \${SCOUT_*} from this"
echo "  shell's environment FIRST and falls back to .env only for names the"
echo "  shell does not export. An exported SCOUT_ENDPOINT therefore wins over"
echo "  the one in .env, and editing .env will not move your telemetry until"
echo "  you unset it (unset SCOUT_ENDPOINT ... , or start the stack under"
echo "  env -i) and recreate the collector."
COLLECTOR_CID=$(cd "$PROJECT_DIR" && docker compose ps -q otel-collector 2>/dev/null | head -1)
if [ -n "$COLLECTOR_CID" ]; then
    EFFECTIVE_ENDPOINT=$(docker inspect "$COLLECTOR_CID" \
        --format '{{range .Config.Env}}{{println .}}{{end}}' 2>/dev/null \
        | sed -n 's/^SCOUT_ENDPOINT=//p' | head -1)
    echo "  Endpoint the running collector was actually started with:"
    echo "    ${EFFECTIVE_ENDPOINT:-<empty>}"
    echo "  That is the tenant this run will export to, whatever .env says."
fi

echo ""
echo "[4/8] Profile isolation"
# otelcol_exporter_sent_spans is collector-global, so a second WordPress
# server feeding the same collector makes the delta unattributable - the
# Apache profile's 10s HTTP healthcheck alone produces real spans forever.
# Refuse to measure until the target is the only WordPress server up.
if [ "$APACHE_PORT" = "$FPM_PORT" ]; then
    echo "  FAIL - WP_APACHE_PORT and WP_FPM_PORT are both $APACHE_PORT, so the"
    echo "  target cannot be identified from SITE_URL. Give them distinct values."
    exit 1
fi
TARGET_PORT="${SITE_URL##*:}"
TARGET_PORT="${TARGET_PORT%%/*}"
case "$TARGET_PORT" in
    "$APACHE_PORT")
        TARGET_LABEL="Apache + mod_php"
        TARGET_SERVICES="wordpress"
        RIVAL_SERVICES="wordpress-fpm nginx"
        ;;
    "$FPM_PORT")
        TARGET_LABEL="PHP-FPM + nginx"
        TARGET_SERVICES="nginx wordpress-fpm"
        RIVAL_SERVICES="wordpress"
        ;;
    *)
        echo "  FAIL - SITE_URL port '$TARGET_PORT' matches neither WP_APACHE_PORT"
        echo "  ($APACHE_PORT) nor WP_FPM_PORT ($FPM_PORT), so this script cannot tell"
        echo "  which profile you are verifying - and it cannot then tell whether the"
        echo "  other profile is contaminating the collector's counters. Export the"
        echo "  same WP_APACHE_PORT / WP_FPM_PORT values you started the stack with."
        exit 1
        ;;
esac
RUNNING=$(cd "$PROJECT_DIR" && docker compose ps --services --status running 2>/dev/null)
if ! printf '%s\n' "$RUNNING" | grep -qx otel-collector; then
    echo "  FAIL - 'docker compose ps' in $PROJECT_DIR does not list a running"
    echo "  otel-collector, so this script cannot see the Compose project whose"
    echo "  metrics it is reading and cannot check which WordPress servers are up."
    echo "  Run it from a shell where 'docker compose ps' resolves this project."
    exit 1
fi
for svc in $TARGET_SERVICES; do
    if ! printf '%s\n' "$RUNNING" | grep -qx "$svc"; then
        echo "  FAIL - target is $TARGET_LABEL but its '$svc' service is not running."
        echo "  Start it first: docker compose ps   (run from $PROJECT_DIR)"
        exit 1
    fi
done
CONTAMINATING=""
for svc in $RIVAL_SERVICES; do
    if printf '%s\n' "$RUNNING" | grep -qx "$svc"; then
        CONTAMINATING="${CONTAMINATING}${CONTAMINATING:+ }$svc"
    fi
done
if [ -n "$CONTAMINATING" ]; then
    echo "  FAIL - target is $TARGET_LABEL, but these services from the other"
    echo "  profile are also running: $CONTAMINATING"
    echo "  They emit spans into the same collector, and the counters this script"
    echo "  reads are collector-global - with both profiles up, a run can pass on"
    echo "  the other profile's traffic while the target emits nothing. The Apache"
    echo "  profile does this on its own: its healthcheck GETs / every 10s."
    echo "  Stop them, then re-run:"
    echo "    docker compose stop $CONTAMINATING   (run from $PROJECT_DIR)"
    exit 1
fi
echo "  OK - $TARGET_LABEL is the only WordPress server running ($TARGET_SERVICES)"

echo ""
echo "[5/8] Confirming $SITE_URL responds"
SITE_CODE=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "$SITE_URL/" 2>/dev/null)
SITE_CODE="${SITE_CODE:-000}"
if [ "$SITE_CODE" = "000" ]; then
    echo "  FAIL - nothing answered at $SITE_URL"
    echo "  Check WP_APACHE_PORT / WP_FPM_PORT and that the profile you mean to"
    echo "  test is actually up (docker compose ps, run from $PROJECT_DIR), or"
    echo "  set SITE_URL explicitly - it defaults to the Apache profile"
    echo "  (http://localhost:$APACHE_PORT), not the FPM profile."
    exit 1
fi
if [ "$SITE_CODE" != "200" ]; then
    echo "  FAIL - $SITE_URL/ answered HTTP $SITE_CODE, not 200."
    echo "  The path set expects 200 at /, so this run would measure error pages,"
    echo "  not WordPress. A 500 usually means the DB connection or the seed step"
    echo "  failed; a 502 means nginx cannot reach PHP-FPM. Check:"
    echo "    docker compose ps && docker compose logs --tail 50   (from $PROJECT_DIR)"
    exit 1
fi
echo "  OK - got HTTP 200"
# This probe's own spans would otherwise flush after the baseline read and be
# counted as if the traffic run had produced them. Let them land first.
echo "  Letting this probe's spans flush before the baseline read..."
sleep "$FLUSH_WAIT"

metric_value() {
    # $1 = metric name, $2 = label match, e.g. exporter="otlp_http/scout".
    # Sums every matching series - a metric can carry more label dimensions
    # than the one matched on (e.g. otelcol_receiver_accepted_spans also
    # varies by transport), so more than one line can legitimately match.
    # Each line is parsed by splitting on the closing '}' of its label set
    # and taking the first token after it - not the last field, which can
    # be an optional Prometheus trailing timestamp - then that token must be
    # a plain non-negative integer or this fails loudly instead of silently
    # miscomparing a float/NaN/scientific-notation value.
    local m="$1" label="$2" lines line value total=0
    lines=$(curl -s --max-time 10 "$COLLECTOR_METRICS" 2>/dev/null | grep -E "^${m}\{[^}]*${label}[^}]*\}")
    if [ -z "$lines" ]; then
        echo 0
        return 0
    fi
    while IFS= read -r line; do
        value=$(printf '%s\n' "$line" | sed -E 's/^[^{]*\{[^}]*\}[[:space:]]+//' | awk '{print $1}')
        if ! [[ "$value" =~ ^[0-9]+$ ]]; then
            echo "FAIL - ${m}{${label}} is not a plain non-negative integer: '${value}'" >&2
            echo "  Line: ${line}" >&2
            echo "  Cannot safely compare. Inspect $COLLECTOR_METRICS directly." >&2
            return 1
        fi
        total=$((total + value))
    done <<< "$lines"
    echo "$total"
}

SENT_BEFORE=$(metric_value otelcol_exporter_sent_spans "exporter=\"${EXPORTER_ID}\"") || exit 1
FAILED_BEFORE=$(metric_value otelcol_exporter_send_failed_spans "exporter=\"${EXPORTER_ID}\"") || exit 1
RECEIVED_BEFORE=$(metric_value otelcol_receiver_accepted_spans "receiver=\"${RECEIVER_ID}\"") || exit 1

echo ""
echo "[6/8] Generating traffic against $SITE_URL"
if ! SITE_URL="$SITE_URL" "$PROJECT_DIR/scripts/test-api.sh" > /dev/null; then
    echo "  FAIL - test-api.sh did not pass against $SITE_URL; fix the site before checking export"
    exit 1
fi
echo "  OK - path set completed against $SITE_URL"

echo "  Waiting for the collector's batch timeout and an export attempt..."
sleep "$FLUSH_WAIT"

SENT_AFTER=$(metric_value otelcol_exporter_sent_spans "exporter=\"${EXPORTER_ID}\"") || exit 1
FAILED_AFTER=$(metric_value otelcol_exporter_send_failed_spans "exporter=\"${EXPORTER_ID}\"") || exit 1
RECEIVED_AFTER=$(metric_value otelcol_receiver_accepted_spans "receiver=\"${RECEIVER_ID}\"") || exit 1

SENT_DELTA=$((SENT_AFTER - SENT_BEFORE))
FAILED_DELTA=$((FAILED_AFTER - FAILED_BEFORE))
RECEIVED_DELTA=$((RECEIVED_AFTER - RECEIVED_BEFORE))

echo ""
echo "[7/8] Collector metrics (source: $COLLECTOR_METRICS)"
echo "  These counters are collector-wide, not per-server. [4/8] is what makes"
echo "  the deltas below attributable to $SITE_URL."
echo "  otelcol_receiver_accepted_spans{receiver=\"$RECEIVER_ID\"}    before=$RECEIVED_BEFORE  after=$RECEIVED_AFTER  (delta $RECEIVED_DELTA)"
echo "  otelcol_exporter_sent_spans{exporter=\"$EXPORTER_ID\"}        before=$SENT_BEFORE  after=$SENT_AFTER  (delta $SENT_DELTA)"
echo "  otelcol_exporter_send_failed_spans{exporter=\"$EXPORTER_ID\"} before=$FAILED_BEFORE  after=$FAILED_AFTER  (delta $FAILED_DELTA)"

echo ""
echo "[8/8] Export verdict for $SITE_URL"
RESULT=0

if [ "$SENT_DELTA" -lt 0 ] || [ "$FAILED_DELTA" -lt 0 ] || [ "$RECEIVED_DELTA" -lt 0 ]; then
    echo "  FAIL - a counter went backwards during this run, so the collector"
    echo "  restarted mid-measurement and the before/after pair is not comparable."
    echo "  Re-run once the collector has been up for the whole window:"
    echo "    docker compose ps otel-collector   (run from $PROJECT_DIR)"
    RESULT=1
elif [ "$RECEIVED_DELTA" -lt "$SPAN_DELTA_FLOOR" ]; then
    # Production floor, checked before the export floor. sent_spans counts what
    # the exporter shipped in the window, which is not the same as what the
    # target produced in the window: a retry that clears inside
    # max_elapsed_time (300s) releases spans queued earlier and can carry
    # sent_spans past the floor while the target sits silent. Gating the
    # receiver counter too closes that door at no extra cost - both counters
    # move together on a healthy run.
    echo "  FAIL - the collector accepted only $RECEIVED_DELTA new spans during this"
    echo "  run, under the floor of $SPAN_DELTA_FLOOR that a full 8-path run has to"
    echo "  clear (see SPAN_DELTA_FLOOR in this script for how the floor is derived"
    echo "  from the path set). otelcol_receiver_accepted_spans is collector-wide -"
    echo "  every span accepted from any sender - so a reading this low means the"
    echo "  collector was barely sent anything at all. Since [4/8] confirmed the"
    echo "  target is the only WordPress server up, that points at $SITE_URL rather"
    echo "  than at export: check that instrumentation is active and that requests"
    echo "  are succeeding: SITE_URL=$SITE_URL ./scripts/test-api.sh, then"
    echo "  docker compose logs otel-collector | grep 'Span #'"
    if [ "$SENT_DELTA" -ge "$SPAN_DELTA_FLOOR" ]; then
        echo "  Note: sent_spans did rise, by $SENT_DELTA. With the receiver counter"
        echo "  flat that is a backlog draining - spans queued before this run and"
        echo "  released as a retry cleared - not traffic this run produced. That is"
        echo "  exactly why the pass condition gates both counters, not just"
        echo "  sent_spans."
    fi
    RESULT=1
elif [ "$SENT_DELTA" -lt "$SPAN_DELTA_FLOOR" ]; then
    echo "  FAIL - sent_spans to Scout rose by $SENT_DELTA over this run, under the"
    echo "  floor of $SPAN_DELTA_FLOOR that a full 8-path run has to clear (see"
    echo "  SPAN_DELTA_FLOOR in this script for how the floor is derived from the"
    echo "  path set). A small non-zero delta here is stray traffic, not your run."
    echo "  otelcol_receiver_accepted_spans rose by $RECEIVED_DELTA over the same"
    echo "  window, clearing the same floor, so the collector did get this run's"
    echo "  spans and did not ship them. That points at export, not at $SITE_URL:"
    echo "  check SCOUT_ENDPOINT, SCOUT_CLIENT_ID, SCOUT_CLIENT_SECRET,"
    echo "  SCOUT_TOKEN_URL (the values the collector was started with are printed"
    echo "  in [3/8]), and network reachability from inside the collector's"
    echo "  container. A retryable failure can take up to max_elapsed_time (300s)"
    echo "  before it shows up as send_failed_spans below - this may still be in"
    echo "  flight; re-run to check again."
    RESULT=1
fi

if [ "$FAILED_DELTA" -gt 0 ]; then
    echo "  FAIL - send_failed_spans to Scout gained $FAILED_DELTA new failures"
    echo "  during this run. Export is failing for at least some spans. Check"
    echo "  SCOUT_ENDPOINT, SCOUT_CLIENT_ID, SCOUT_CLIENT_SECRET, SCOUT_TOKEN_URL"
    echo "  (see the effective endpoint printed in [3/8]), then:"
    echo "    docker compose up -d --force-recreate otel-collector"
    RESULT=1
fi

if [ "$RESULT" -eq 0 ]; then
    echo "  OK - the collector accepted $RECEIVED_DELTA new spans and exported"
    echo "  $SENT_DELTA to Scout during this run, from the only WordPress server"
    echo "  running ($TARGET_LABEL at $SITE_URL), with no new send failures."
    echo "  That is export confirmed, not queryability: nothing here queries Scout."
    echo ""
    echo "Open Scout and filter on service.name=wordpress-mariadb-otel"
else
    echo ""
    echo "Spans from $SITE_URL are not confirmed reaching Scout. See the FAIL lines above."
fi

exit "$RESULT"
