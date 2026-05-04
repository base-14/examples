# Azure AKS Telemetry - OpenTelemetry Operator

Provision an AKS cluster, install cert-manager + the OpenTelemetry Operator
+ kube-state-metrics, deploy three operator-managed
`OpenTelemetryCollector` CRs (agent DaemonSet, cluster Deployment, control-plane Deployment using `azure_monitor`), then auto-instrument 4 sample apps
(Python, Node.js, Java, Go-eBPF) via a single `Instrumentation` CR.

Customer-facing guide:
<https://docs.base14.io/instrument/infra/azure/aks/>

> **Cost:** 1 × `Standard_B4s_v2` ≈ $0.17/hr at single-node steady state; budget ~$1 for a short demo. **Always tear down when done.**

## Run

```bash
set -a; . ~/.config/base14/scout-otel-config.env; set +a

infra/provision.sh --dry-run         # free preview
infra/provision.sh                   # 10-15 min; cost meter starts
scripts/deploy-sample-apps.sh        # ~2 min
scripts/capture-observed.sh          # writes observed-metrics-<UTC>.md

infra/teardown.sh                    # mandatory
```

## Files

- `infra/main.bicep` + modules + `provision.sh` + `teardown.sh`.
- `manifests/00..07-` - ordered apply: cert-manager, operator, namespace,
  3 collector CRs, Instrumentation CR, KSM.
- `manifests/sample-apps/{lang}/` - annotated Deployment + ConfigMap-mounted
  source per language.
- `scripts/install-addons.sh`, `deploy-sample-apps.sh`, `capture-observed.sh`.
- `observed-metrics.md` - metric names emitted by each of the 3 collectors, resource attributes attached, and pipeline shape.
