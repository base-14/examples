# DNS Resolution Failures

Symptoms: "no such host" / "name resolution failed" errors; intermittent timeouts
to internal services; failures that clear on retry.
Likely causes: an overloaded or crashing CoreDNS, a bad ConfigMap, NodeLocal DNS
issues, or upstream resolver timeouts.
Diagnostics: `kubectl -n kube-system get pods -l k8s-app=kube-dns`; test from a pod
with `nslookup <svc>`; check CoreDNS logs and the DNS request/error metrics.
Remediation: restart or scale CoreDNS, fix the Corefile ConfigMap, raise resolver
timeouts, and add caching. Verify lookups succeed from an affected pod.
Escalation: page the platform team if CoreDNS is healthy but upstream DNS fails.
