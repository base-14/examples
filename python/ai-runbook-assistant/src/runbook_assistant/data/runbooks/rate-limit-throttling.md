# Rate Limiting / Throttling

Symptoms: a surge of HTTP 429 responses; clients retrying and backing off; latency
rising as requests are queued or rejected at the edge.
Likely causes: a client exceeding its quota, a too-tight limit after a traffic
change, a retry storm amplifying load, or an upstream API throttling us.
Diagnostics: check the 429 rate and which client/route dominates; review the limiter
config and current quota; grep logs for "rate limit" / "throttled".
Remediation: raise or right-size the limit, add jittered backoff on the client,
cache hot responses, or shard the quota per tenant. Confirm 429s subside.
Escalation: contact the upstream provider if the throttling originates on their side.
