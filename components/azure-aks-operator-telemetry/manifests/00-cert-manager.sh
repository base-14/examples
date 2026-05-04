#!/usr/bin/env bash
# Installs cert-manager v1.20.2 (operator's webhook needs it for TLS certs).
# Idempotent: re-applies are safe.

set -euo pipefail

CERT_MANAGER_VERSION="v1.20.2"

echo "==> Applying cert-manager $CERT_MANAGER_VERSION"
kubectl apply -f "https://github.com/cert-manager/cert-manager/releases/download/$CERT_MANAGER_VERSION/cert-manager.yaml"

echo "==> Waiting for cert-manager Deployments to be Available (5 min timeout)"
kubectl wait --for=condition=Available deployment/cert-manager -n cert-manager --timeout=300s
kubectl wait --for=condition=Available deployment/cert-manager-webhook -n cert-manager --timeout=300s
kubectl wait --for=condition=Available deployment/cert-manager-cainjector -n cert-manager --timeout=300s

echo "==> cert-manager ready"
