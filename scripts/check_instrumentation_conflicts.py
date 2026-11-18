"""Fail when an installed OpenTelemetry instrumentation cannot instrument its library.

Usage, from a project directory: uv run --no-sync python ../../scripts/check_instrumentation_conflicts.py

An instrumentation that finds its library outside the version range it supports logs a
warning and instruments nothing. Upgrading a library past that range removes its spans
without any error, so upgrade-deps.sh runs this after every Python upgrade. A library
that is not installed at all is not a conflict.
"""

import sys
from importlib.metadata import entry_points


def main() -> int:
    try:
        from opentelemetry.instrumentation.dependencies import get_dependency_conflicts
    except ImportError:
        return 0
    conflicts = []
    for entry_point in entry_points(group="opentelemetry_instrumentor"):
        try:
            instrumentor = entry_point.load()()
            requirements = instrumentor.instrumentation_dependencies()
        except Exception:
            continue
        conflict = get_dependency_conflicts(requirements)
        if conflict is not None and getattr(conflict, "found", None):
            conflicts.append(f"  {entry_point.name}: {conflict}")
    for line in conflicts:
        print(line)
    return 1 if conflicts else 0


if __name__ == "__main__":
    sys.exit(main())
