"""Persistence models owned by Incidents (PostgreSQL / SQLAlchemy 2.x)."""
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, Index, String, func, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class IncidentModel(Base):
    __tablename__ = "incidents_incidents"
    __table_args__ = (
        CheckConstraint("title = 'HTTP monitor unavailable'", name="ck_incidents_title"),
        CheckConstraint("severity = 'critical'", name="ck_incidents_severity"),
        CheckConstraint("status IN ('OPEN', 'ACKNOWLEDGED', 'RESOLVED')", name="ck_incidents_status"),
        Index(
            "uq_incidents_one_active_per_monitor",
            "monitor_id",
            unique=True,
            postgresql_where=text("status IN ('OPEN', 'ACKNOWLEDGED')"),
        ),
    )

    owner_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    # Cross-service reference: stored as UUID, without a database foreign key.
    monitor_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(24), nullable=False, default="HTTP monitor unavailable", server_default=text("'HTTP monitor unavailable'"))
    severity: Mapped[str] = mapped_column(String(8), nullable=False, default="critical", server_default=text("'critical'"))
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="OPEN", server_default=text("'OPEN'"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class ProcessedEventModel(Base):
    __tablename__ = "incidents_processed_events"

    # Broker event UUID used to make consume/retry idempotent.
    event_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
