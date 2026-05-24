#!/usr/bin/env bash
# One-command boot for the constrained-device demo.
#
# Brings up the non-firmware services (mosquitto + sme-bridge + Collector),
# then builds the firmware and launches it in the Wokwi simulator if the
# toolchain is present. Without the toolchain it leaves the services running
# and tells you how to feed them a device stand-in.
set -euo pipefail
cd "$(dirname "$0")/.."

if [ -z "${SCOUT_CLIENT_ID:-}" ]; then
  echo "Scout env not set. Run: source ~/.config/base14/scout-otel-config.env" >&2
  echo "(or copy .env.example to .env and fill it in)" >&2
  exit 1
fi

echo "Starting services..."
docker compose up -d --build

echo "Waiting for the bridge to become healthy..."
for _ in $(seq 1 30); do
  if [ "$(docker inspect -f '{{.State.Health.Status}}' mcu-sme-bridge 2>/dev/null)" = "healthy" ]; then
    break
  fi
  sleep 2
done

if command -v idf.py >/dev/null 2>&1 && command -v wokwi-cli >/dev/null 2>&1; then
  echo "Building firmware..."
  (cd firmware && idf.py build)
  echo "Launching Wokwi (test.mosquitto.org broker; set a unique TOPIC_PREFIX to avoid collisions)..."
  wokwi-cli firmware/wokwi --timeout 0
else
  echo
  echo "ESP-IDF / wokwi-cli not found, services are up without firmware."
  echo "Feed the bridge a device stand-in instead:"
  echo "    ./scripts/publish-sample.sh --loop"
  echo
  echo "To run the real firmware, install ESP-IDF v5.5 and the Wokwi CLI, then"
  echo "re-run this script. See README.md."
fi
