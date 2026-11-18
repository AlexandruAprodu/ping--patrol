"""Persistence models owned by Monitoring (PostgreSQL / SQLAlchemy 2.x)."""
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, Integer, String, func, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class MonitorModel(Base):
    __tablename__ = "monitoring_monitors"
    __table_args__ = (
        CheckConstraint("length(btrim(name)) BETWEEN 1 AND 100", name="ck_monitoring_name"),
        CheckConstraint("interval_seconds BETWEEN 5 AND 3600", name="ck_monitoring_interval"),
        CheckConstraint("failure_threshold BETWEEN 1 AND 10", name="ck_monitoring_threshold"),
    )

    owner_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    url: Mapped[str] = mapped_column(String(2083), nullable=False)
    interval_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=60, server_default=text("60"))
    failure_threshold: Mapped[int] = mapped_column(Integer, nullable=False, default=3, server_default=text("3"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
