# Scrape Target Down

Symptoms: a Prometheus target shows up=0; metrics for the service go stale; alerts
fire for missing data rather than a real fault.
Likely causes: the metrics endpoint is unreachable, the pod is down or not ready,
a wrong port/path in the ServiceMonitor, or a network policy blocking the scrape.
Diagnostics: check the Prometheus targets page for the scrape error; curl the
`/metrics` endpoint from inside the cluster; verify the ServiceMonitor selector.
Remediation: fix the endpoint or port, correct the ServiceMonitor, or allow the
scrape in the network policy. Confirm the target returns to up=1.
Escalation: page monitoring owners if targets stay down after the config fix.
