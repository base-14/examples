"""Move the exact `==` pins in a pyproject.toml to the newest release in the same major version.

Usage: uv run --no-project --with packaging python scripts/bump_exact_pins.py <pyproject.toml>

`uv lock --upgrade` never moves an exact pin, so upgrade-deps.sh calls this first. A final
release moves only to final releases; a pre-release (0.66b2, 1.3b0) may move to a newer
pre-release. All bumps are locked together. If `uv lock` fails, each bump is tried on its
own and only the ones that lock are kept. Prints `name old -> new` for every kept bump.
"""

import json
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

from packaging.version import InvalidVersion, Version

PIN = re.compile(r'"([A-Za-z0-9][A-Za-z0-9._-]*)(\[[^\]]*\])?==([^";\s]+)"')


def newest_same_major(name: str, current: Version) -> Version | None:
    url = f"https://pypi.org/pypi/{name}/json"
    try:
        with urllib.request.urlopen(url, timeout=20) as response:
            releases = json.load(response)["releases"]
    except Exception:
        return None
    best = None
    for raw, files in releases.items():
        if not files or all(f.get("yanked") for f in files):
            continue
        try:
            candidate = Version(raw)
        except InvalidVersion:
            continue
        if candidate.major != current.major or candidate <= current:
            continue
        if candidate.is_prerelease and not current.is_prerelease:
            continue
        if best is None or candidate > best:
            best = candidate
    return best


def locks(project: Path) -> bool:
    return subprocess.run(["uv", "lock"], cwd=project, capture_output=True).returncode == 0


def main() -> int:
    pyproject = Path(sys.argv[1]).resolve()
    project = pyproject.parent
    original = pyproject.read_text()

    bumps = {}
    for name, extras, raw in PIN.findall(original):
        try:
            current = Version(raw)
        except InvalidVersion:
            continue
        newer = newest_same_major(name, current)
        if newer is not None:
            bumps[(name, extras or "", raw)] = str(newer)

    def apply(text: str, keys) -> str:
        for name, extras, raw in keys:
            text = text.replace(f'"{name}{extras}=={raw}"', f'"{name}{extras}=={bumps[(name, extras, raw)]}"')
        return text

    if not bumps:
        return 0
    pyproject.write_text(apply(original, bumps))
    if locks(project):
        kept = list(bumps)
    else:
        kept, text = [], original
        for key in bumps:
            trial = apply(text, [key])
            pyproject.write_text(trial)
            if locks(project):
                kept.append(key)
                text = trial
        pyproject.write_text(text)
        if not locks(project):
            pyproject.write_text(original)
            return 1

    for name, extras, raw in kept:
        print(f"  {name} {raw} -> {bumps[(name, extras, raw)]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
