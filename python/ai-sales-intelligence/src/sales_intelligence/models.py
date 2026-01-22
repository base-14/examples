"""ORM models for AI Sales Intelligence."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from sales_intelligence.database import Base


class Connection(Base):
    """LinkedIn connection imported from CSV."""

    __tablename__ = "connections"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str | None] = mapped_column(String(255))
    company: Mapped[str | None] = mapped_column(String(255))
    position: Mapped[str | None] = mapped_column(String(255))
    connected_on: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # FTS index created via migration:
    # CREATE INDEX idx_connections_fts ON connections
    # USING gin(to_tsvector('english', first_name || ' ' || last_name || ' ' || company));


class Campaign(Base):
    """Sales campaign with targeting criteria."""

    __tablename__ = "campaigns"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255))
    target_keywords: Mapped[str | None] = mapped_column(Text)
    target_titles: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(50), default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    prospects: Mapped[list[Prospect]] = relationship(back_populates="campaign")


class Prospect(Base):
    """Enriched and scored prospect."""

    __tablename__ = "prospects"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="CASCADE")
    )
    connection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("connections.id", ondelete="CASCADE")
    )

    # Enrichment data
    enrichment: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    # Scoring
    icp_score: Mapped[int | None] = mapped_column(Integer)
    score_reasoning: Mapped[str | None] = mapped_column(Text)

    # Email draft
    email_subject: Mapped[str | None] = mapped_column(String(255))
    email_body: Mapped[str | None] = mapped_column(Text)

    # Evaluation
    quality_score: Mapped[int | None] = mapped_column(Integer)
    quality_passed: Mapped[bool | None] = mapped_column(default=None)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    campaign: Mapped[Campaign] = relationship(back_populates="prospects")

    __table_args__ = (Index("idx_prospects_campaign_id", "campaign_id"),)
