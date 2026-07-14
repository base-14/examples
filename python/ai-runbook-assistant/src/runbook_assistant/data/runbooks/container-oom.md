# Container OOMKilled

Symptoms: pods restart with reason OOMKilled; memory usage near the cgroup limit;
CrashLoopBackOff after repeated kills.
Likely causes: memory limit set too low, a leak, or a load spike.
Diagnostics: `kubectl describe pod <pod>` (Last State: OOMKilled); check the
memory metric vs the limit; grep logs for "OOMKilled".
Remediation: raise the memory limit or fix the leak; roll the deployment; if a
spike, scale out. Verify restarts stop.
Escalation: page the service owner if OOMKills continue after a limit bump.
