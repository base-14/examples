# Node Memory Pressure

Symptoms: kubelet reports MemoryPressure; pods evicted by priority; system slows
as it reclaims memory; OOMKills across unrelated pods on the same node.
Likely causes: overcommitted memory requests, a noisy-neighbor pod, or too few
nodes for the scheduled load.
Diagnostics: check node memory metrics; `kubectl top nodes` and `kubectl top pods
--all-namespaces` to find the heaviest consumers; review eviction events.
Remediation: cordon and drain if needed, add capacity or scale the node pool, set
realistic requests/limits, and reschedule the offending workload.
Escalation: page the capacity owner if pressure recurs after adding nodes.
