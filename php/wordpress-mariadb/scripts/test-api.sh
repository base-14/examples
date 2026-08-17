#!/bin/bash
# Drives the fixed path set the guide's span counts are written against.
# Changing this path set invalidates them.

set -uo pipefail

SITE_URL="${SITE_URL:-http://localhost:8080}"
PASSED=0
FAILED=0

check() {
    local label="$1" path="$2" expected="$3"
    local code
    # --max-time: a target that accepts the connection and never answers would
    # otherwise hang this script, and verify-scout.sh with it.
    code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 15 "${SITE_URL}${path}")
    if [ "$code" = "$expected" ]; then
        echo "[PASS] ${label} (${code})"
        PASSED=$((PASSED + 1))
    else
        echo "[FAIL] ${label} - expected ${expected}, got ${code} (${path})"
        FAILED=$((FAILED + 1))
    fi
}

echo "=== WordPress OpenTelemetry path set ==="
echo "Target: ${SITE_URL}"
echo ""

check "home"        "/"                              200
check "single post" "/first-post/"                   200
check "page"        "/about/"                        200
check "archive"     "/category/observability/"       200
check "search"      "/?s=scout"                      200
check "rest posts"  "/wp-json/wp/v2/posts"           200
check "login page"  "/wp-login.php"                  200
check "not found"   "/this-path-does-not-exist/"     404

echo ""
echo "Passed: ${PASSED}  Failed: ${FAILED}"
[ "$FAILED" -eq 0 ]
