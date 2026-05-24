#!/usr/bin/env bash
# Prove the battery-aware filter: a low-battery device on a non-critical fleet
# has its metrics dropped at the edge, while a critical device on the same low
# battery still reports. Traces are unaffected - the filter is metrics-only.
#
# Usage: scripts/simulate-low-battery.sh
set -euo pipefail
cd "$(dirname "$0")/.."

echo "==> Restarting sensor-001 at battery level 15 (priority=normal)"
DEVICE_BATTERY_LEVEL=15 docker compose up -d --no-deps --force-recreate producer

echo "==> Launching sensor-critical at battery level 15 (priority=critical)"
DEVICE_BATTERY_LEVEL=15 FLEET_PRIORITY=critical DEVICE_ID=sensor-critical \
  docker compose run -d --no-deps --name edge-producer-critical producer

cat <<'EOF'

==> In Scout, watch iot.sensor.temperature by device.id:
      - sensor-001      stops arriving  (dropped at the edge to save battery)
      - sensor-critical keeps arriving  (critical fleets bypass the filter)
    Both devices' traces continue to flow either way.

    Reset to normal:
      docker compose rm -sf edge-producer-critical
      docker compose up -d --no-deps --force-recreate producer
EOF
