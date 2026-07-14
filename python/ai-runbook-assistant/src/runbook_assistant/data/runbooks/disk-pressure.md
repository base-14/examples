# Node Disk Pressure

Symptoms: kubelet reports DiskPressure; pods evicted; "no space left on device"
errors; ephemeral-storage near 100%.
Likely causes: log files or container images filling the disk, a runaway write,
or an undersized volume.
Diagnostics: check the node disk metric; `kubectl describe node <node>` for the
DiskPressure condition; find large dirs with `du -sh /var/lib/*`.
Remediation: prune unused images (`crictl rmi --prune`), rotate or ship logs off
the node, expand the volume, or move the workload. Confirm pressure clears.
Escalation: page the infra on-call if the node stays under pressure after cleanup.
