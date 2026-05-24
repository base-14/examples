#!/usr/bin/env bash
# Publish a sample SME-v1 envelope to the local broker, standing in for the
# ESP32 firmware when you do not want to run Wokwi. Doubles as a fuzz helper
# for the bridge: --malformed and --bad-version exercise its reject paths.
#
# Usage:
#   ./scripts/publish-sample.sh                 # one valid telemetry envelope
#   ./scripts/publish-sample.sh --loop          # a reading every 10s, Ctrl-C to stop
#   ./scripts/publish-sample.sh --offline       # a Last Will / offline message
#   ./scripts/publish-sample.sh --malformed     # invalid JSON (parse_errors_total)
#   ./scripts/publish-sample.sh --bad-version   # v:999 (version_rejected_total)
set -euo pipefail
cd "$(dirname "$0")/.."

PREFIX="${TOPIC_PREFIX:-scout/mcu}"
DEVICE_ID="${DEVICE_ID:-esp32-dev-01}"

pub() { docker compose exec -T mosquitto mosquitto_pub -h localhost -t "$1" -q 1 -m "$2"; }

rand_hex() { head -c "$1" /dev/urandom | xxd -p | tr -d '\n'; }

telemetry_envelope() {
  local now_ms temp uptime sine traceparent
  now_ms=$(($(date +%s) * 1000))
  uptime=${SECONDS}
  # A plausible CPU temp and a slow sine, so charts in Scout move.
  temp=$(awk -v s="$uptime" 'BEGIN { printf "%.1f", 41 + 3 * sin(s / 30.0) }')
  sine=$(awk -v s="$uptime" 'BEGIN { printf "%.3f", sin(s / 15.0) }')
  traceparent="00-$(rand_hex 16)-$(rand_hex 8)-01"
  cat <<JSON
{"v":1,"device":{"id":"${DEVICE_ID}","model":"esp32-s3-devkitc","firmware":{"version":"0.1.0","channel":"dev"},"fleet":{"id":"fleet-demo","tenant":"acme"}},"ts_ms":${now_ms},"ts_source":"sntp","trace":{"traceparent":"${traceparent}"},"metrics":[{"name":"mcu.cpu.temp_c","kind":"gauge","value":${temp},"unit":"Cel"},{"name":"mcu.uptime","kind":"counter","value":${uptime},"unit":"s"},{"name":"mcu.synthetic.sine","kind":"gauge","value":${sine},"unit":"1"}],"events":[{"name":"wifi.reconnect","severity":"warn","attrs":{"rssi":-78}}]}
JSON
}

case "${1:-}" in
  --offline)
    pub "${PREFIX}/${DEVICE_ID}/offline" \
      "{\"v\":1,\"device\":{\"id\":\"${DEVICE_ID}\",\"fleet\":{\"id\":\"fleet-demo\"}},\"reason\":\"lwt\"}"
    echo "published offline for ${DEVICE_ID}"
    ;;
  --malformed)
    pub "${PREFIX}/${DEVICE_ID}/telemetry" "{not valid json"
    echo "published malformed payload"
    ;;
  --bad-version)
    pub "${PREFIX}/${DEVICE_ID}/telemetry" \
      "{\"v\":999,\"device\":{\"id\":\"${DEVICE_ID}\"},\"ts_ms\":0,\"metrics\":[]}"
    echo "published bad-version envelope"
    ;;
  --loop)
    echo "publishing every 10s to ${PREFIX}/${DEVICE_ID}/telemetry (Ctrl-C to stop)"
    while true; do
      pub "${PREFIX}/${DEVICE_ID}/telemetry" "$(telemetry_envelope)"
      echo "published reading at $(date -u +%H:%M:%S)"
      sleep 10
    done
    ;;
  *)
    pub "${PREFIX}/${DEVICE_ID}/telemetry" "$(telemetry_envelope)"
    echo "published one telemetry envelope for ${DEVICE_ID}"
    ;;
esac
