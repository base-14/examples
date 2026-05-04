#!/usr/bin/env bash
# Installs the in-cluster stack in order. Called by infra/provision.sh after
# kubeconfig is fetched. Idempotent; safe to re-run.
#
# Required env: KUBECONFIG, AKS_UAMI_CLIENT_ID, AZURE_SUBSCRIPTION_ID,
#               AZURE_REGION, AZURE_RESOURCE_GROUP, AKS_CLUSTER_NAME,
#               AKS_RESOURCE_ID, ENVIRONMENT,
#               SCOUT_CLIENT_ID, SCOUT_CLIENT_SECRET, SCOUT_TOKEN_URL,
#               SCOUT_OTLP_ENDPOINT.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
MANIFESTS="$ROOT_DIR/manifests"

for v in KUBECONFIG AKS_UAMI_CLIENT_ID AZURE_SUBSCRIPTION_ID AZURE_REGION \
         AZURE_RESOURCE_GROUP AKS_CLUSTER_NAME AKS_RESOURCE_ID \
         SCOUT_CLIENT_ID SCOUT_CLIENT_SECRET SCOUT_TOKEN_URL SCOUT_OTLP_ENDPOINT; do
  [ -n "${!v:-}" ] || { echo "ERROR: $v not set" >&2; exit 1; }
done

echo "==> 00 cert-manager"
"$MANIFESTS/00-cert-manager.sh"

echo "==> 01 operator"
"$MANIFESTS/01-operator.sh"

echo "==> 02 namespace + secrets + configmap"
kubectl apply -f "$MANIFESTS/02-namespace-secrets.yaml"

# scout-oauth2 Secret (created imperatively to avoid plaintext in repo).
kubectl create secret generic scout-oauth2 -n otel \
  --from-literal=SCOUT_CLIENT_ID="$SCOUT_CLIENT_ID" \
  --from-literal=SCOUT_CLIENT_SECRET="$SCOUT_CLIENT_SECRET" \
  --from-literal=SCOUT_TOKEN_URL="$SCOUT_TOKEN_URL" \
  --from-literal=SCOUT_OTLP_ENDPOINT="$SCOUT_OTLP_ENDPOINT" \
  --dry-run=client -o yaml | kubectl apply -f -

# otel-azure-context ConfigMap.
kubectl create configmap otel-azure-context -n otel \
  --from-literal=AZURE_SUBSCRIPTION_ID="$AZURE_SUBSCRIPTION_ID" \
  --from-literal=AZURE_REGION="$AZURE_REGION" \
  --from-literal=AZURE_RESOURCE_GROUP="$AZURE_RESOURCE_GROUP" \
  --from-literal=AKS_CLUSTER_NAME="$AKS_CLUSTER_NAME" \
  --from-literal=AKS_RESOURCE_ID="$AKS_RESOURCE_ID" \
  --dry-run=client -o yaml | kubectl apply -f -

echo "==> 03..05 collector CRs (apply, then annotate SAs after operator creates them)"
kubectl apply -f "$MANIFESTS/03-collector-agent.yaml"
kubectl apply -f "$MANIFESTS/04-collector-cluster.yaml"
kubectl apply -f "$MANIFESTS/05-collector-control-plane.yaml"

# The operator creates SAs from spec.serviceAccount within ~10s of CR apply.
# Wait for them, then patch the WI annotation in.
for SA in otel-agent otel-cluster otel-control-plane; do
  echo "==> Waiting for SA $SA"
  for _ in {1..30}; do
    kubectl get sa "$SA" -n otel >/dev/null 2>&1 && break
    sleep 2
  done
  kubectl annotate sa "$SA" -n otel \
    "azure.workload.identity/client-id=$AKS_UAMI_CLIENT_ID" --overwrite
done

# Workload Identity propagation lag (30-60s after federation lands at apply).
echo "==> Waiting 60s for Workload Identity token propagation"
sleep 60

# Restart collector pods so the projected token is mounted (operator names
# the workloads <cr-name>-collector).
kubectl rollout restart daemonset/otel-agent-collector -n otel || true
kubectl rollout restart deployment/otel-cluster-collector -n otel || true
kubectl rollout restart deployment/otel-control-plane-collector -n otel || true

echo "==> 06 Instrumentation CR"
kubectl apply -f "$MANIFESTS/06-instrumentation.yaml"

echo "==> 07 kube-state-metrics"
"$MANIFESTS/07-kube-state-metrics.sh"

echo "==> Waiting for collector pods Ready (5 min)"
kubectl wait --for=condition=Ready pod -l app.kubernetes.io/name=otel-agent -n otel --timeout=300s
kubectl wait --for=condition=Ready pod -l app.kubernetes.io/name=otel-cluster -n otel --timeout=300s
kubectl wait --for=condition=Ready pod -l app.kubernetes.io/name=otel-control-plane -n otel --timeout=300s

echo "==> Install-addons complete"
