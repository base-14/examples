"""Async SQLAlchemy engine/session + Diagnosis model + persistence.

Each /diagnose request is persisted here, producing a real SQLAlchemy INSERT
span in the unified trace. trace_id links the row back to its trace.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Diagnosis(Base):
    __tablename__ = "diagnoses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    service: Mapped[str | None] = mapped_column(String(64), nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer)
    trace_id: Mapped[str | None] = mapped_column(String(32), nullable=True)


def make_engine(database_url: str) -> AsyncEngine:
    return create_async_engine(database_url, pool_pre_ping=True)


def make_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def init_db(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def save_diagnosis(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    question: str,
    answer: str,
    service: str | None,
    duration_ms: int,
    trace_id: str | None,
) -> str:
    did = str(uuid.uuid4())
    async with session_factory() as session:
        session.add(
            Diagnosis(
                id=did,
                created_at=datetime.now(UTC),
                question=question,
                answer=answer,
                service=service,
                duration_ms=duration_ms,
                trace_id=trace_id,
            )
        )
        await session.commit()
    return did
