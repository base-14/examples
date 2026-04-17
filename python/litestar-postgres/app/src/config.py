"""Runtime configuration loaded from environment variables.

Kept tiny on purpose — Litestar/uvicorn already read most OTEL_* vars on their
own. This module only owns the two settings we care about in app code.
"""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str
    notify_url: str

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            database_url=os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./articles.db"),
            notify_url=os.getenv("NOTIFY_URL", "http://localhost:8081/notify"),
        )
