# Database Connection Pool Exhaustion

Symptoms: "timeout acquiring connection from pool" errors; p99 latency rises;
requests queue waiting for a connection; pool reports all connections in use.
Likely causes: pool sized too small, connections leaked (not returned), long-running
or slow queries holding connections, or a traffic surge.
Diagnostics: check pool in-use vs max and wait-time metrics; grep logs for "pool
exhausted" / "timeout acquiring connection"; look for slow queries holding sessions.
Remediation: fix leaks (ensure sessions close), tune the pool size and statement
timeout, optimize the slow query, or scale read replicas. Watch waits drop.
Escalation: involve the DBA if the database itself is saturated or maxed on
connections.
