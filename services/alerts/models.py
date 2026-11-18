"""Persistence models owned by Alerts (PostgreSQL / SQLAlchemy 2.x)."""
from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class AlertEventModel(Base):
    __tablename__ = "alerts_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('incident_detected', 'incident_resolved')",
            name="ck_alerts_event_type",
        ),
    )

    # Incoming event UUID is the primary key for idempotent redelivery handling.
    event_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    owner_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    incident_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    # Snapshot from Incidents REST; SSE still delivers only to current connections.
    incident_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
