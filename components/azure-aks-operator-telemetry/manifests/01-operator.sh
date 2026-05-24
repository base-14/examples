#!/usr/bin/env bash
# Installs the OpenTelemetry Operator via Helm chart v0.111.0 (operator v0.150.0).
# Pinned chart version for stable CRD schema; pinned manager image so we don't
# silently move when ghcr's :latest moves.

set -euo pipefail

OPERATOR_CHART_VERSION="0.111.0"
OPERATOR_NAMESPACE="opentelemetry-operator-system"

echo "==> Adding open-telemetry helm repo"
helm repo add open-telemetry https://open-telemetry.github.io/opentelemetry-helm-charts >/dev/null 2>&1 || true
helm repo update open-telemetry >/dev/null

echo "==> Installing opentelemetry-operator chart $OPERATOR_CHART_VERSION"
helm upgrade --install opentelemetry-operator open-telemetry/opentelemetry-operator \
  --version "$OPERATOR_CHART_VERSION" \
  --namespace "$OPERATOR_NAMESPACE" \
  --create-namespace \
  --set "manager.collectorImage.repository=otel/opentelemetry-collector-contrib" \
  --set "manager.collectorImage.tag=0.152.1" \
  --wait --timeout 5m

echo "==> Waiting for operator Deployment Available"
kubectl wait --for=condition=Available \
  deployment/opentelemetry-operator -n "$OPERATOR_NAMESPACE" --timeout=300s

echo "==> Operator ready"
