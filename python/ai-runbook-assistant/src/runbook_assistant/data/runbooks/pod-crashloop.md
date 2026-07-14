# Pod CrashLoopBackOff

Symptoms: a pod repeatedly starts and exits; status shows CrashLoopBackOff with a
growing backoff delay; restart count climbing.
Likely causes: a failing readiness/liveness probe, a missing config or secret, a
bad image, or the process exiting non-zero on startup.
Diagnostics: `kubectl describe pod <pod>` for the last exit code and events;
`kubectl logs <pod> --previous` to read the crashed container's output.
Remediation: fix the failing config or probe, roll back a bad image, or correct
the startup command; redeploy and watch the restart count settle.
Escalation: if the crash is in a shared base image or platform component, escalate
to the platform team.
