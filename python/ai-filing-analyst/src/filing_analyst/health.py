import json
from pathlib import Path
from typing import Any

import psycopg


def count_facts(dsn: str) -> int:
    with psycopg.connect(dsn, connect_timeout=3) as conn:
        row = conn.execute("SELECT count(*) FROM facts").fetchone()
    return int(row[0]) if row else 0


def fixture_date(fixtures_dir: Path) -> str | None:
    manifest = fixtures_dir / "MANIFEST.json"
    if not manifest.exists():
        return None
    data: dict[str, Any] = json.loads(manifest.read_text())
    fetched = data.get("fetched")
    return str(fetched) if fetched else None
