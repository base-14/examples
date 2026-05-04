#!/usr/bin/env bash
# Tears down the demo: best-effort helm uninstalls (so RBAC + finalizers
# clear cleanly), then deletes the RG (which removes everything else).
# Idempotent.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
ENV_FILE="$ROOT_DIR/.env"
KUBECONFIG_FILE="$ROOT_DIR/kubeconfig.yaml"

[ -f "$ENV_FILE" ] || { echo "ERROR: $ENV_FILE not found. Nothing to tear down." >&2; exit 1; }

set -a; . "$ENV_FILE"; set +a

echo "==> Tearing down RG: $AZURE_RESOURCE_GROUP"
read -r -p "Confirm delete (yes/no)? " ans
[ "$ans" = "yes" ] || { echo "Aborted."; exit 0; }

if [ -f "$KUBECONFIG_FILE" ]; then
  export KUBECONFIG="$KUBECONFIG_FILE"
  echo "==> Best-effort helm uninstall (30s timeout each)"
  timeout 30 helm uninstall opentelemetry-operator -n opentelemetry-operator-system 2>/dev/null || true
  timeout 30 helm uninstall kube-state-metrics -n kube-state-metrics 2>/dev/null || true
fi

echo "==> az group delete --no-wait"
az group delete --name "$AZURE_RESOURCE_GROUP" --yes --no-wait

echo "==> Local cleanup"
rm -f "$KUBECONFIG_FILE" "$ENV_FILE"

echo "==> Done. RG deletion runs async in Azure (5-10 min)."
