#!/bin/bash
# Generates all three signals (traces, metrics, logs) from both the backend and a
# headless browser, so you can confirm them in base14 Scout (or the collector's
# debug exporter). Run with the stack up: `docker compose up --build`.
#
# Env overrides: API_URL, FRONTEND_URL, COLLECTOR_HEALTH_URL, CHROME_BIN, CDP_PORT.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
API_URL="${API_URL:-http://localhost:3000}"
FRONTEND_URL="${FRONTEND_URL:-http://localhost:8080}"
COLLECTOR_HEALTH_URL="${COLLECTOR_HEALTH_URL:-http://localhost:13133}"
CDP_PORT="${CDP_PORT:-9222}"
PASS=0
FAIL=0

green() { echo -e "\033[32m$1\033[0m"; }
red() { echo -e "\033[31m$1\033[0m"; }
blue() { echo -e "\033[34m$1\033[0m"; }
yellow() { echo -e "\033[33m$1\033[0m"; }

CHROME_PID=""
PROFILE_DIR=""
cleanup() {
  if [ -n "$CHROME_PID" ]; then
    kill "$CHROME_PID" 2>/dev/null
    wait "$CHROME_PID" 2>/dev/null  # let Chrome reap its helper processes before rm
  fi
  [ -n "$PROFILE_DIR" ] && rm -rf "$PROFILE_DIR" 2>/dev/null
}
trap cleanup EXIT

blue "============================================"
blue "Scout/OpenTelemetry Verification"
blue "Angular Full-Stack OpenTelemetry"
blue "============================================"
echo ""

# --- Step 1: OTel Collector health -----------------------------------------
blue "=== Step 1: OTel Collector Health ==="
CODE=$(curl -s -o /dev/null -w "%{http_code}" "$COLLECTOR_HEALTH_URL/" 2>/dev/null || echo "000")
if [ "$CODE" = "200" ]; then
  green "✓ OTel Collector is healthy"
  ((PASS++))
else
  red "✗ OTel Collector not responding (HTTP $CODE) - is 'docker compose up' running?"
  ((FAIL++))
fi
echo ""

# --- Step 2: Backend signals (trace + http metric + pino log) --------------
blue "=== Step 2: Backend Traffic (trace + http.server.request.duration + pino log) ==="
CODE=$(curl -s -o /dev/null -w "%{http_code}" "$API_URL/healthz" 2>/dev/null || echo "000")
if [ "$CODE" = "200" ]; then
  green "✓ API is healthy"
  ((PASS++))
else
  red "✗ API not responding (HTTP $CODE)"
  ((FAIL++))
fi

echo "Generating successful requests (GET /api/items x3)..."
for i in 1 2 3; do curl -s -o /dev/null "$API_URL/api/items"; done
CODE=$(curl -s -o /dev/null -w "%{http_code}" "$API_URL/api/items" 2>/dev/null || echo "000")
[ "$CODE" = "200" ] && { green "✓ /api/items served (backend trace + http metric + 'served items' pino log)"; ((PASS++)); } \
                     || { red "✗ /api/items failed (HTTP $CODE)"; ((FAIL++)); }

echo "Generating a 404 (GET /api/missing)..."
CODE=$(curl -s -o /dev/null -w "%{http_code}" "$API_URL/api/missing" 2>/dev/null || echo "000")
[ "$CODE" = "404" ] && { green "✓ /api/missing returned 404 (error trace)"; ((PASS++)); } \
                     || { yellow "! /api/missing returned $CODE (expected 404)"; }
echo ""

# --- Step 3: Browser signals (spans + web vitals metrics + error logs) ------
blue "=== Step 3: Browser Drive (spans + web_vitals metrics + error logs) ==="
find_chrome() {
  for b in "$CHROME_BIN" \
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
    "/Applications/Chromium.app/Contents/MacOS/Chromium" \
    "$(command -v google-chrome 2>/dev/null)" \
    "$(command -v chromium 2>/dev/null)" \
    "$(command -v chromium-browser 2>/dev/null)"; do
    [ -n "$b" ] && [ -x "$b" ] && { echo "$b"; return 0; }
  done
  return 1
}

CHROME="$(find_chrome)"
if [ -z "$CHROME" ]; then
  yellow "! No Chrome/Chromium found - skipping the headless browser drive."
  yellow "  Test the browser leg manually: open $FRONTEND_URL/items and click"
  yellow "  Load items / Trigger API error / Trigger error, then switch tabs."
  yellow "  (Set CHROME_BIN=/path/to/chrome to enable the automated drive.)"
elif ! command -v node >/dev/null 2>&1; then
  yellow "! node not found - skipping the headless browser drive (needed for the CDP driver)."
else
  PROFILE_DIR="$(mktemp -d)"
  "$CHROME" --headless=new --remote-debugging-port="$CDP_PORT" '--remote-allow-origins=*' \
    --user-data-dir="$PROFILE_DIR" --no-first-run --no-default-browser-check \
    about:blank >/dev/null 2>&1 &
  CHROME_PID=$!

  echo "Launched headless Chrome (pid $CHROME_PID); waiting for CDP on :$CDP_PORT..."
  READY=""
  for i in $(seq 1 20); do
    curl -s "http://localhost:$CDP_PORT/json/version" >/dev/null 2>&1 && { READY=1; break; }
    sleep 1
  done

  if [ -z "$READY" ]; then
    red "✗ Chrome CDP did not come up on :$CDP_PORT"
    ((FAIL++))
  else
    green "✓ CDP ready - driving the SPA"
    if CDP_URL="http://localhost:$CDP_PORT" FRONTEND_URL="$FRONTEND_URL" \
         node "$SCRIPT_DIR/drive-browser.mjs"; then
      green "✓ Browser drive completed (browser spans, web_vitals metrics, 2 error logs)"
      ((PASS++))
    else
      red "✗ Browser drive failed"
      ((FAIL++))
    fi
  fi
fi
echo ""

# --- Summary ----------------------------------------------------------------
blue "=== What to look for in Scout ==="
echo "  Services : angular-browser (browser), angular-items-api (backend)"
echo "  Traces   : one 'Load items' trace spans browser HTTP GET -> GET /api/items -> pg.query"
echo "  Metrics  : web_vitals.{lcp,inp,cls,fcp,ttfb} + http.server.request.duration + runtime-node"
echo "  Logs     : backend pino (trace_id/span_id); browser interceptor ERROR log (correlated)"
echo "             and ErrorHandler ERROR log (best-effort, no trace id)"
echo "  No creds? Watch the local debug exporter: docker compose logs -f otel-collector"
echo ""
blue "============================================"
if [ "$FAIL" -eq 0 ]; then
  green "PASS: $PASS checks passed, $FAIL failed"
else
  red "DONE: $PASS passed, $FAIL failed"
fi
blue "============================================"
exit 0
