# Maintenance scripts

Run these by hand from the repository root during maintenance. They sweep every example project, skipping the legacy projects
(`go119-gin191-postgres`, `ruby27-rails52-mysql8`, `ruby30-rails61-mysql`, `php8-laravel8-sqlite`, `php84-slim3-mongodb`,
`express-typescript-mongodb`). Legacy projects are pinned on purpose, so they take no dependency, collector, or clean sweeps.
The list is held in `SKIP_PROJECTS` in `check-outdated.sh`, `upgrade-deps.sh` and `clean.sh`, and in `LEGACY_PROJECTS` in
`verify-collector-bump.sh` — change all four together.

## `clean.sh` — reclaim disk and reset docker state

Two verbs, both run by default:

- `clean` removes a project's build artifacts, caches, and vendored deps (`node_modules`, `dist`, `_build`, `target`, and so on) using
  the project's own `make clean` or `npm run clean`.
- `reset` runs `docker compose down -v --remove-orphans` for any project with a compose file, dropping its containers and named volumes.
  Before each teardown it sources `~/.config/base14/scout-otel-config.env` (override with `$SCOUT_OTLP_CONFIG`) so compose files that
  require Scout variables such as `${SCOUT_OTLP_ENDPOINT:?...}` can be interpolated.

This is destructive and is not wired into any schedule. Preview with `--dry-run`, then scope with `--language` before a full sweep.

```bash
./scripts/clean.sh --dry-run            # preview the whole fleet
./scripts/clean.sh --language nodejs    # scoped run once the preview looks right
./scripts/clean.sh                      # full-fleet clean + reset
```

| Flag             | Effect                                                                        |
|------------------|-------------------------------------------------------------------------------|
| `--language <dir>` | Restrict to one top-level dir (`nodejs`, `go`, `components`, ...). Default: all. |
| `--clean-only`   | Only remove build artifacts and caches; skip docker teardown.                 |
| `--reset-only`   | Only tear down docker; skip artifact cleanup.                                 |
| `--prune-images` | Add `--rmi local` to `reset`, dropping images the compose project built.      |
| `--dry-run`      | Show what would run; change nothing.                                          |

Projects without a `clean` target and without a compose file are reported as skipped rather than silently ignored. A `clean` target
lives in each project's `Makefile`, or as a `clean` script in its `package.json`; `reset` needs no per-project setup.

## Dependency maintenance

- `check-outdated.sh` reports outdated dependencies across the example projects. For gradle projects it injects the
  ben-manes versions plugin via `gradle-versions.init.gradle`, so the six gradle builds need no plugin of their own.
- `upgrade-deps.sh` runs a blanket dependency upgrade (optionally scoped to the OTel family) and verifies each project.
- `update-libraries.sh` applies curated, hand-picked `package@version` bumps from `library-updates.txt` and verifies build/lint.
- `verify-collector-bump.sh` runs `test-api.sh` and `verify-scout.sh` per project after an OTel Collector version bump.
