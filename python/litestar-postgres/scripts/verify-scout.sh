#!/usr/bin/env bash
# End-to-end OpenTelemetry pipeline verification.
#
# Brings up the full compose stack, drives traffic, then asserts that the
# collector saw:
#   1. JSON logs with trace correlation (otelTraceID in records)
#   2. A distributed trace with spans from BOTH services sharing trace_id
#   3. The custom `articles.created` counter incremented to N
#
# If SCOUT_CLIENT_ID is set, also asserts that the otlphttp/b14 exporter
# succeeded (no 4xx/5xx in its output) — useful in CI with real Scout creds.
#
# Collector logs are written to a real temp file (mktemp); piping into a
# bash variable silently truncates at ~2 MB on macOS.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

POSTS=${POSTS:-3}
LOGS_FILE=$(mktemp -t litestar-collector-logs.XXXXXX)
SUMMARY_FILE=$(mktemp -t litestar-verify-summary.XXXXXX)
trap 'rm -f "$LOGS_FILE" "$SUMMARY_FILE"' EXIT

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; NC='\033[0m'
PASS=0; FAIL=0
pass() { echo -e "${GREEN}PASS${NC} $1"; PASS=$((PASS+1)); }
fail() { echo -e "${RED}FAIL${NC} $1"; FAIL=$((FAIL+1)); }

echo -e "${YELLOW}=== verify-scout: bringing up stack ===${NC}"
START_TIME=$(date -u +%Y-%m-%dT%H:%M:%SZ)
docker compose down -v >/dev/null 2>&1 || true
docker compose up -d --build >/dev/null

echo "    waiting for app to become healthy..."
for _ in $(seq 1 30); do
    if curl -fsS http://localhost:8080/api/health >/dev/null 2>&1; then break; fi
    sleep 1
done
curl -fsS http://localhost:8080/api/health >/dev/null || { fail "app not healthy"; exit 1; }

echo "    posting $POSTS article(s)..."
for i in $(seq 1 "$POSTS"); do
    curl -fsS -X POST http://localhost:8080/api/articles \
        -H 'Content-Type: application/json' \
        -d "{\"title\":\"verify-$i\",\"body\":\"verify-scout body $i\"}" >/dev/null
done

# Wait long enough for: BSP flush (2s), metric interval (10s), collector batch (10s).
echo "    waiting 25s for collector to flush traces/logs/metrics..."
sleep 25

docker compose logs --since="$START_TIME" otel-collector > "$LOGS_FILE" 2>&1
echo "    collector log size: $(wc -l < "$LOGS_FILE") lines"

echo
echo -e "${YELLOW}=== assertions ===${NC}"

# 1. JSON logs with trace correlation
docker compose logs --since="$START_TIME" app 2>&1 | grep -q '"otelTraceID":' \
    && pass "app emits JSON logs with otelTraceID" \
    || fail "app missing JSON logs / trace correlation"
docker compose logs --since="$START_TIME" notify 2>&1 | grep -q '"otelTraceID":' \
    && pass "notify emits JSON logs with otelTraceID" \
    || fail "notify missing JSON logs / trace correlation"

# 2. Distributed trace — at least one trace_id appears under both service names
python3 - "$LOGS_FILE" > "$SUMMARY_FILE" <<'PY'
import re, sys, collections
text = open(sys.argv[1]).read()
trace_to_services = collections.defaultdict(set)
current_service = None
current_tid = None
for line in text.splitlines():
    m = re.search(r"service\.name: Str\(([^)]+)\)", line)
    if m: current_service = m.group(1); continue
    m = re.search(r"Trace ID\s*:\s*([0-9a-f]{16,})", line)
    if m and current_service:
        trace_to_services[m.group(1)].add(current_service)

shared = [t for t, svcs in trace_to_services.items()
          if {"litestar-postgres-app", "litestar-postgres-notify"}.issubset(svcs)]
print(f"shared_traces={len(shared)}")
PY
SHARED=$(grep -oE 'shared_traces=[0-9]+' "$SUMMARY_FILE" | cut -d= -f2)
[ "${SHARED:-0}" -ge 1 ] \
    && pass "found $SHARED distributed trace(s) spanning both services" \
    || fail "no distributed trace shared between articles + notify"

# 3. articles.created metric
LAST_VALUE=$(awk '
    /-> Name: articles.created/ { hit=1; next }
    hit && /Value:/ { gsub(/.*Value: /,""); print; hit=0 }
' "$LOGS_FILE" | tail -1)
[ -n "$LAST_VALUE" ] && [ "$LAST_VALUE" -ge "$POSTS" ] \
    && pass "articles.created counter exported (last value=$LAST_VALUE >= $POSTS)" \
    || fail "articles.created counter missing or below $POSTS (got '${LAST_VALUE:-none}')"

# 4. filter/noisy drops asyncpg transaction-lifecycle spans
if grep -Eq '^ +Name +: (BEGIN|COMMIT|ROLLBACK)(;| TRANSACTION)?$' "$LOGS_FILE"; then
    fail "filter/noisy missed BEGIN/COMMIT/ROLLBACK spans — check otel-config.yaml regex"
else
    pass "filter/noisy dropped BEGIN/COMMIT/ROLLBACK spans"
fi

# 5. Scout exporter health (only if creds were provided)
if [ -n "${SCOUT_CLIENT_ID:-}" ]; then
    if grep -q "otlp_http/b14.*Exporting failed" "$LOGS_FILE"; then
        fail "Scout exporter reported failures (check SCOUT_* env)"
    else
        pass "Scout exporter — no failures observed"
    fi
else
    echo "    (skipping Scout exporter check — SCOUT_CLIENT_ID not set)"
fi

echo
echo -e "${YELLOW}=== Summary: $PASS passed, $FAIL failed ===${NC}"
docker compose down >/dev/null 2>&1 || true
[ "$FAIL" -eq 0 ]
