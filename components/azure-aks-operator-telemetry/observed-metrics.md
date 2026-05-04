# Emitted Metrics

This component deploys three operator-managed OpenTelemetry collectors on AKS, plus four auto-instrumented sample apps. The collectors emit ~190+ distinct metric names depending on cluster activity, plus sample-app traces, metrics, and logs over OTLP.

| Collector | Controller | Scope |
|---|---|---|
| `otel-agent` | DaemonSet | Node-level signals + OTLP ingress for sample apps |
| `otel-cluster` | Deployment | Cluster state via `kube-state-metrics` (Prometheus) + `k8s_cluster` receiver |
| `otel-control-plane` | Deployment | AKS control-plane metrics via `azure_monitor` receiver |

Scrape intervals: 10s on agent + cluster collectors, 60s on control-plane (Azure Monitor ingestion lag floor).

---

## otel-agent (DaemonSet)

### `kubeletstatsreceiver` — node, pod, container, and volume signals from the kubelet Summary API

```
container.cpu.time
container.cpu.usage
container.filesystem.available
container.filesystem.capacity
container.filesystem.usage
container.memory.available
container.memory.major_page_faults
container.memory.page_faults
container.memory.rss
container.memory.usage
container.memory.working_set
container.uptime
k8s.container.cpu_limit_utilization
k8s.container.cpu_request_utilization
k8s.container.memory_limit_utilization
k8s.container.memory_request_utilization
k8s.node.cpu.time
k8s.node.cpu.usage
k8s.node.filesystem.available
k8s.node.filesystem.capacity
k8s.node.filesystem.usage
k8s.node.memory.available
k8s.node.memory.major_page_faults
k8s.node.memory.page_faults
k8s.node.memory.rss
k8s.node.memory.usage
k8s.node.memory.working_set
k8s.node.network.errors
k8s.node.network.io
k8s.node.uptime
k8s.pod.cpu.time
k8s.pod.cpu.usage
k8s.pod.cpu_limit_utilization
k8s.pod.cpu_request_utilization
k8s.pod.filesystem.available
k8s.pod.filesystem.capacity
k8s.pod.filesystem.usage
k8s.pod.memory.available
k8s.pod.memory.major_page_faults
k8s.pod.memory.page_faults
k8s.pod.memory.rss
k8s.pod.memory.usage
k8s.pod.memory.working_set
k8s.pod.memory_limit_utilization
k8s.pod.memory_request_utilization
k8s.pod.network.errors
k8s.pod.network.io
k8s.pod.uptime
k8s.volume.available
k8s.volume.capacity
k8s.volume.inodes
k8s.volume.inodes.free
k8s.volume.inodes.used
```

**Conditionally emitted (depend on workload shape):**

- `k8s.container.cpu.node.utilization`, `k8s.container.memory.node.utilization`, `k8s.pod.cpu.node.utilization`, `k8s.pod.memory.node.utilization` — the `*.node.utilization` family computes usage / node_capacity and emits on longer-running clusters.
- `k8s.pod.volume.usage` — only when a pod has a PVC mount; pods using ConfigMap or emptyDir do not produce this series.

### `hostmetricsreceiver` — 22 metric names across 9 scrapers

```
system.cpu.load_average.15m
system.cpu.load_average.1m
system.cpu.load_average.5m
system.cpu.time
system.disk.io
system.disk.io_time
system.disk.merged
system.disk.operation_time
system.disk.operations
system.disk.pending_operations
system.disk.weighted_io_time
system.filesystem.inodes.usage
system.filesystem.usage
system.memory.usage
system.network.connections
system.network.dropped
system.network.errors
system.network.io
system.network.packets
system.processes.count
system.processes.created
system.uptime
```

Scrapers enabled: `cpu`, `disk`, `filesystem`, `load`, `memory`, `network`, `paging`, `processes`, `system`.

### `otlp` receiver (from sample apps)

Accepts traces, metrics, and logs from the four auto-instrumented sample apps (`python-fastapi`, `nodejs-express`, `java-spring`, `go-ebpf`) over OTLP/HTTP. Auto-instrumented apps emit:

- **Spans** for HTTP request handling.
- **Metrics**: RED-style HTTP duration histograms + request counters by default.
- **Logs**: structured log records (Python especially).

---

## otel-cluster (Deployment)

### `prometheus` → `kube-state-metrics`

Full set of `kube_*` series flowing through (~85 names depending on KSM's enabled collectors). Representative groups:

```
kube_certificatesigningrequest_*  (3)
kube_configmap_*                  (2)
kube_daemonset_*                  (9)
kube_deployment_*                 (10)
kube_endpointslice_*              (3)
kube_lease_*
kube_namespace_*
kube_node_*                       (multiple)
kube_pod_*                        (multiple)
kube_poddisruptionbudget_*        (5)
kube_replicaset_*                 (7)
kube_secret_*                     (4)
kube_service_*                    (3)
kube_storageclass_*               (2)
kube_validatingwebhookconfiguration_*  (3)
scrape_samples_post_metric_relabeling
scrape_samples_scraped
scrape_series_added
up
```

### `k8s_cluster` receiver

Emits `k8s.*` cluster-state metrics (deployments, replicasets, pods, namespaces, nodes) when cluster state changes. Idle clusters with no workload churn may emit no series in short capture windows.

---

## otel-control-plane (Deployment)

### `azure_monitor` receiver — 9 whitelisted metrics × 2 aggregations = 18 series

```
azure_apiserver_cpu_usage_percentage_average
azure_apiserver_cpu_usage_percentage_maximum
azure_apiserver_memory_usage_percentage_average
azure_apiserver_memory_usage_percentage_maximum
azure_etcd_cpu_usage_percentage_average
azure_etcd_cpu_usage_percentage_maximum
azure_etcd_database_usage_percentage_average
azure_etcd_database_usage_percentage_maximum
azure_etcd_memory_usage_percentage_average
azure_etcd_memory_usage_percentage_maximum
azure_cluster_autoscaler_cluster_safe_to_autoscale_average
azure_cluster_autoscaler_cluster_safe_to_autoscale_total
azure_cluster_autoscaler_scale_down_in_cooldown_average
azure_cluster_autoscaler_scale_down_in_cooldown_total
azure_cluster_autoscaler_unneeded_nodes_count_average
azure_cluster_autoscaler_unneeded_nodes_count_total
azure_cluster_autoscaler_unschedulable_pods_count_average
azure_cluster_autoscaler_unschedulable_pods_count_total
```

The `azure_cluster_autoscaler_*` metrics emit zero values when the autoscaler is enabled but the node pool is pinned (`minCount == maxCount`). Set `maxCount: 2` or higher for non-zero data.

---

## Resource attributes attached to every metric

```
cloud.provider:               azure
cloud.platform:               azure_aks
cloud.account.id:             <subscription-id>
cloud.region:                 <azure-region>
k8s.cluster.name:             <cluster-name>
deployment.environment.name:  <environment>
deployment.environment:       <environment>
environment:                  <environment>
service.name:                 otel-agent | otel-cluster | aks-control-plane
```

Plus the operator-injected pod context: `host.name`, `k8s.namespace.name`, `k8s.node.ip`, `k8s.node.name`, `k8s.pod.ip`, `k8s.pod.name`.

---

## Pipeline shape

| Signal | Source receivers (per collector) | Exporter |
|---|---|---|
| Spans | `otel-agent`: `otlp` (from sample apps) | `otlp_http/b14` (Scout) |
| Metrics | `otel-agent`: `hostmetrics` + `kubeletstats` + `otlp` | `otlp_http/b14` (Scout) |
| Metrics | `otel-cluster`: `prometheus` (KSM) + `k8s_cluster` | `otlp_http/b14` (Scout) |
| Metrics | `otel-control-plane`: `azure_monitor` | `otlp_http/b14` (Scout) |
| Logs | `otel-agent`: `otlp` (from sample apps) | `otlp_http/b14` (Scout) |
