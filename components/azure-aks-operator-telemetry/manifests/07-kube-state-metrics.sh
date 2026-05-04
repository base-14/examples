#!/usr/bin/env bash
# Installs kube-state-metrics via Helm so the cluster collector's prometheus
# receiver has a target.

set -euo pipefail

KSM_NAMESPACE="kube-state-metrics"

echo "==> Adding prometheus-community helm repo"
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts >/dev/null 2>&1 || true
helm repo update prometheus-community >/dev/null

echo "==> Installing kube-state-metrics"
helm upgrade --install kube-state-metrics prometheus-community/kube-state-metrics \
  --namespace "$KSM_NAMESPACE" --create-namespace --wait --timeout 5m

echo "==> KSM ready"
