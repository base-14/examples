# Elevated p99 Latency

Symptoms: p99 (and often p95) request latency climbs while p50 stays flat; timeouts
upstream; queueing under load.
Likely causes: a slow dependency or query, lock/pool contention, GC pauses, or an
undersized replica count.
Diagnostics: check the latency histogram and which endpoint regressed; trace a slow
request to find the dominant span; look for DB pool waits or slow queries.
Remediation: add an index or cache the slow path, raise the connection pool or
replica count, and set sensible timeouts. Confirm p99 returns to baseline.
Escalation: involve the data team if a database query is the bottleneck.
