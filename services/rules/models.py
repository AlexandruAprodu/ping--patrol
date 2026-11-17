"""Persistence models owned by Rules Engine (PostgreSQL / SQLAlchemy 2.x)."""
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, Integer, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class RuleStateModel(Base):
    __tablename__ = "rules_states"
    __table_args__ = (
        CheckConstraint("consecutive_failures >= 0", name="ck_rules_failures_nonnegative"),
    )

    # UUID belongs to a monitor in another service; deliberately no cross-service FK.
    monitor_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    alerting: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
