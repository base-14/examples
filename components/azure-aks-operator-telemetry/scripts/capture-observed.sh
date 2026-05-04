#!/usr/bin/env bash
# Captures observed metrics + spans by temporarily switching the debug exporter
# to verbosity: detailed, sleeping a couple of scrape cycles, then reverting.

set -euo pipefail

OUT="observed-$(date -u +%Y%m%dT%H%M%SZ).txt"

echo "==> Bumping debug verbosity to detailed"
for cr in otel-agent otel-cluster otel-control-plane; do
  kubectl patch opentelemetrycollector "$cr" -n otel --type=json \
    -p='[{"op":"replace","path":"/spec/config/exporters/debug/verbosity","value":"detailed"}]'
done

echo "==> Waiting 90s for two scrape cycles + emit"
sleep 90

echo "==> Capturing logs to $OUT"
{
  echo "## Agent (DaemonSet) - kubeletstats + hostmetrics"
  kubectl logs -n otel -l app.kubernetes.io/name=otel-agent --tail=2000 | grep -E "Name:|Trace ID:" | sort -u
  echo ""
  echo "## Cluster (Deployment) - k8s_cluster + prometheus"
  kubectl logs -n otel -l app.kubernetes.io/name=otel-cluster --tail=2000 | grep -E "Name:" | sort -u
  echo ""
  echo "## Control plane (Deployment) - azure_monitor"
  kubectl logs -n otel -l app.kubernetes.io/name=otel-control-plane --tail=2000 | grep -E "Name:" | sort -u
} > "$OUT"

echo "==> Reverting debug verbosity to basic"
for cr in otel-agent otel-cluster otel-control-plane; do
  kubectl patch opentelemetrycollector "$cr" -n otel --type=json \
    -p='[{"op":"replace","path":"/spec/config/exporters/debug/verbosity","value":"basic"}]'
done

echo "==> Done. Output: $OUT"
