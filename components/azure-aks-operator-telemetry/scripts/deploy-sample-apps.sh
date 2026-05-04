#!/usr/bin/env bash
# Deploys all 4 sample apps + drives a few HTTP calls per app so traces emit
# immediately instead of waiting for organic traffic.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
APPS_DIR="$ROOT_DIR/manifests/sample-apps"

for app in python-fastapi nodejs-express java-spring go-ebpf; do
  echo "==> Applying $app"
  kubectl apply -f "$APPS_DIR/$app/deployment.yaml"
done

# Java compile-on-startup is slow - give it the longest budget.
echo "==> Waiting for sample-app pods Ready (10 min for Java compile)"
for app in python-fastapi nodejs-express go-ebpf; do
  kubectl wait --for=condition=Ready pod -l "app=$app" -n otel --timeout=300s || \
    echo "WARN: $app not Ready; continuing"
done
kubectl wait --for=condition=Ready pod -l app=java-spring -n otel --timeout=600s || \
  echo "WARN: java-spring not Ready; continuing"

# Drive traffic. Each port-forward is short-lived; sequenced to avoid port collision.
for app in python-fastapi nodejs-express java-spring go-ebpf; do
  case "$app" in
    python-fastapi) PORT=8000 ;;
    nodejs-express) PORT=3000 ;;
    java-spring)    PORT=8080 ;;
    go-ebpf)        PORT=8080 ;;
  esac
  echo "==> Driving traffic on $app:$PORT"
  kubectl port-forward -n otel "service/$app" "$PORT":"$PORT" >/dev/null 2>&1 &
  PF_PID=$!
  sleep 2
  for _ in {1..5}; do curl -s "http://localhost:$PORT/" >/dev/null || true; done
  for _ in {1..2}; do curl -s "http://localhost:$PORT/slow" >/dev/null || true; done
  kill "$PF_PID" 2>/dev/null || true
  wait "$PF_PID" 2>/dev/null || true
done

echo "==> Sample apps deployed; traffic driven"
echo "  Verify traces:  kubectl logs -n otel daemonset.apps/otel-agent-collector --tail=100 | grep -i span"
