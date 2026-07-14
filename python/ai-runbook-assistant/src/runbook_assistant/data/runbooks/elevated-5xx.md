# Elevated 5xx Error Rate

Symptoms: a spike in HTTP 500/502/503 responses; error budget burning fast;
alerts on the service SLO; upstream callers seeing failures.
Likely causes: a bad deploy, a failing dependency, resource exhaustion, or an
unhandled exception path.
Diagnostics: check the error-rate metric and which status codes dominate; grep
logs for 5xx and stack traces; correlate the spike with the last deploy time.
Remediation: if it tracks a deploy, roll back; if a dependency is down, shed load
or enable a fallback; scale out if saturated. Watch the error rate recover.
Escalation: declare an incident if the SLO breach persists past the rollback.
