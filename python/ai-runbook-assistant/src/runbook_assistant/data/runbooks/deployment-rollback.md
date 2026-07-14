# Deployment Rollback

Symptoms: errors or latency spike immediately after a release; the regression lines
up with a deploy timestamp; the new ReplicaSet is the one misbehaving.
Likely causes: a regression in the new image, a bad config or migration shipped
with it, or an incompatible dependency bump.
Diagnostics: `kubectl rollout history deployment/<name>`; compare the bad revision
to the last good one; confirm the error onset matches the rollout time.
Remediation: `kubectl rollout undo deployment/<name>` to the last good revision;
verify health and error rate recover; hold the bad image for a fix.
Escalation: notify the release owner and open a regression ticket before re-deploying.
