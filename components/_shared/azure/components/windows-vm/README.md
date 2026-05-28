# windows-vm

Windows Server 2022 Azure VM with IIS feature + idle OTel forwarder
(`OtelCollector` Windows service) installed by the CustomScriptExtension.
For the IIS component example (`examples/components/iis-telemetry/`).
Standard_D2s_v3 default, centralindia -> southindia -> eastus region SKU probe.

## Provision

```bash
./provision.sh                    # default: 8h auto-shutdown
./provision.sh --extend 4         # 4h
./provision.sh --no-auto-shutdown # operator-discipline
```

The provision generates a random `b14admin` password, written to `.endpoint`
(chmod 600, gitignored). RDP via the public IP printed at provision end.
The on-VM forwarder is installed-and-started but idle (its OTLP exporter has
placeholder env vars and fails closed); it has not yet been wired to the
central collector.

## Wire-up (after the central collector is up)

The on-VM forwarder needs the central collector's bearer-token OTLP endpoint
and token. These are surfaced by the otel-discovery `scout-collector` chart
when it is installed into the AKS substrate (per the integration plan's
step 3+) via a chart-owned endpoint ConfigMap. Endpoint-discovery was
formerly an open question (endpoint discovery) in the integration spec;
resolved in otel-discovery slice 18g.

Once `OTLP_GATEWAY_ENDPOINT` and `OTLP_GATEWAY_TOKEN` are known:

```bash
source ./.endpoint
OTLP_GATEWAY_ENDPOINT="<central collector endpoint>"
OTLP_GATEWAY_TOKEN="<token>"
az vm run-command invoke \
  --resource-group "$WINVM_RG" --name "$WINVM_NAME" \
  --command-id RunPowerShellScript \
  --scripts @- <<PS
[Environment]::SetEnvironmentVariable('OTLP_GATEWAY_ENDPOINT', '$OTLP_GATEWAY_ENDPOINT', 'Machine')
[Environment]::SetEnvironmentVariable('OTLP_GATEWAY_TOKEN', '$OTLP_GATEWAY_TOKEN', 'Machine')
Restart-Service -Name OtelCollector
PS
```

Verify the service is exporting (counts advance):

```bash
az vm run-command invoke \
  --resource-group "$WINVM_RG" --name "$WINVM_NAME" \
  --command-id RunPowerShellScript \
  --scripts "(Invoke-WebRequest -UseBasicParsing http://localhost:8888/metrics).Content | Select-String 'otelcol_exporter_sent_metric_points'"
```

## Use the VM (RDP / IIS check)

```bash
source ./.endpoint
echo "RDP to $WINVM_PUBLIC_IP as $WINVM_ADMIN_USER (password in .endpoint)"
# Headless IIS check via az run-command:
az vm run-command invoke --resource-group "$WINVM_RG" --name "$WINVM_NAME" \
  --command-id RunPowerShellScript \
  --scripts "Get-WindowsFeature -Name Web-Server | ConvertTo-Json"
```

## Teardown

```bash
./teardown.sh
```

Refuses to run if `examples/components/iis-telemetry/.installed` marker is
present. Override with `--force`. Always verifies zero residue.

Auto-shutdown via launchd LaunchAgent invokes `teardown.sh --yes --force` at
the expiry deadline -- cost protection at expiry unconditionally bypasses
the components-still-installed guard.

## Cost

Standard_D2s_v3 + Windows license + minimal network in centralindia:
~$0.17/hr. ~$125/mo if forgotten -- the auto-shutdown LaunchAgent
prevents this by default.

## Resources created

| Resource | Count | Notes |
|---|---|---|
| Resource group | 1 | `rg-b14winvm-YYYYMMDD` |
| VM | 1 | Windows Server 2022 (smalldisk image) |
| OS disk | 1 | StandardSSD_LRS |
| NIC | 1 |  |
| NSG | 1 | RDP allow rule pinned to operator's public IP |
| VNet | 1 | 10.10.0.0/16 |
| Public IP | 1 | Static, Standard SKU |
| VM extension | 1 | CustomScriptExtension that installed IIS + OtelCollector service |

Alerting fires `PROVISION-DEVIATION` if RG resource count > 9.

## Security notes

- RDP rule is pinned to the operator's public IP at provision time
  (`curl -s ifconfig.me`). If the operator's network changes mid-session,
  tear down + reprovision OR manually update the NSG rule via
  `az network nsg rule update`.
- Admin password is 20 chars (`openssl rand -base64 18 | head -c 16 + Ab1!`)
  and written to `.endpoint` (chmod 600). Rotate by reprovisioning.
- Owner allow-list applies: set `OWNER_ALLOWLIST` env to override.
- `setupScriptUri` is pinned to an immutable git SHA (no `main` / `master`
  branch refs). The SHA must be reachable on `origin/*` -- a local-only
  commit aborts provision rather than 404'ing the CustomScriptExtension.
- The provisioned `setup-vm.ps1` verifies the otelcol-contrib tarball's
  sha256 against a hardcoded expected value; mismatches fail closed.
- The on-VM forwarder's bearer token (`OTLP_GATEWAY_TOKEN`) is a machine env
  var set by the wire-up step; it rotates whenever the central collector's
  chart is reinstalled. The token never lands in this substrate's `.endpoint`.
- **Token-in-env-var is transient-grade.** A machine-scoped env var on Windows
  is readable by any local admin and visible to any process inheriting from
  the system environment. Acceptable for a dev substrate (single operator,
  ~8h lifetime, per-install rotation); not acceptable for customer-shaped
  product posture. The chart never reaches the customer's Windows hosts, so
  this surface is bounded to this examples-project substrate. A future tighter
  variant would write the token to `C:\ProgramData\OtelCollector\bearer.token`
  with a single-reader ACL and load it from the service's working directory.
- **OTLP TLS is currently `insecure: true`** in setup-vm.ps1's config, meaning
  the bearer token travels cleartext over the public internet to the AKS LB.
  Acceptable only for an 8h dev substrate. The endpoint surfacing mechanism
  is now resolved (otel-discovery slice 18g: chart-owned endpoint ConfigMap).
  A follow-up wire-up step still needs to fetch the cluster's CA so this can
  flip to `insecure: false` before any longer-lived posture.
