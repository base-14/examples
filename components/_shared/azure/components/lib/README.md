# lib/

Cross-cutting guardrail helpers sourced by every substrate
`provision.sh` and `teardown.sh`.

| File | Purpose |
|---|---|
| `alerting.sh`         | osascript + stderr + `$HOME/.local/state/base14-substrate/alerts.log` on deviation / teardown fail |
| `sku-allowlist.sh`    | SKU allow-list, $2.50/hr session cost ceiling, region SKU probe |
| `owner-gate.sh`       | Print provision plan, typed-'yes' confirm, owner allow-list, operator-IP + email resolvers |
| `auto-shutdown.sh`    | launchd LaunchAgent that fires teardown.sh at deadline |
| `teardown-helpers.sh` | Async `wait_rg_gone` with optional caller-provided diagnostic on timeout |

The design spec at
`~/dev/ai/claude-docs/examples-docs/internal/plans/2026-05-27-azure-component-examples-design.md`
contains the cross-reference from the legacy guardrail IDs (G1, G2, ...) to
the helpers above.

## Test policy

Each `.sh` has a paired `tests/<name>.bats`. Run all:

    cd _shared/azure/components
    bats lib/tests/

bats-core via Homebrew: `brew install bats-core`.

## Sourcing order in a substrate `provision.sh`

```bash
LIB="$(cd "$(dirname "$0")/../lib" && pwd)"
source "$LIB/alerting.sh"
source "$LIB/sku-allowlist.sh"
source "$LIB/owner-gate.sh"
source "$LIB/auto-shutdown.sh"
# Also source existing _shared/azure helpers:
source "$(dirname "$0")/../../provision.sh"   # az_shared_* helpers
```
