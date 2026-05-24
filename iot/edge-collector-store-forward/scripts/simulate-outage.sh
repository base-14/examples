#!/usr/bin/env bash
# Cut the backhaul, let the producers keep publishing, and watch the edge
# collector's disk-backed queue grow. Reconnect and watch it drain. Nothing is
# lost: the buffered batches replay with their original timestamps.
#
# Usage: scripts/simulate-outage.sh [outage_seconds]   (default 60)
set -euo pipefail
cd "$(dirname "$0")/.."

OUTAGE="${1:-60}"
EDGE_METRICS="http://localhost:8888/metrics"

queue_size() {
  curl -s "$EDGE_METRICS" \
    | grep -E '^otelcol_exporter_queue_size' \
    | grep 'otlp_http/upstream' \
    | awk '{s += $NF} END {print s + 0}'
}

echo "==> Edge queue depth before outage: $(queue_size)"

echo "==> Cutting the backhaul (disconnect upstream-collector from backhaul-net)"
docker network disconnect backhaul-net upstream-collector

echo "==> Backhaul down for ${OUTAGE}s; producers keep publishing to the edge:"
elapsed=0
while [ "$elapsed" -lt "$OUTAGE" ]; do
  sleep 10
  elapsed=$((elapsed + 10))
  printf '    t+%-3ss  edge queue depth: %s\n' "$elapsed" "$(queue_size)"
done

echo "==> Restoring the backhaul (reconnect upstream-collector)"
docker network connect backhaul-net upstream-collector

echo "==> Waiting 25s for the queue to drain:"
sleep 25
echo "    edge queue depth after recovery: $(queue_size)"

cat <<'EOF'

==> Done. The queue should be back near zero. In Scout, the readings published
    during the outage are present with their original timestamps - the edge held
    them on disk and replayed them once the link returned.
EOF
