"""Persistence model for the local fake-target test fixture (PostgreSQL)."""
from sqlalchemy import CheckConstraint, Integer, SmallInteger, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class FakeTargetModeModel(Base):
    __tablename__ = "fake_target_mode"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_fake_target_singleton"),
        CheckConstraint(
            "status_code BETWEEN 200 AND 599 AND status_code NOT IN (204, 205, 304)",
            name="ck_fake_target_status",
        ),
        CheckConstraint("delay_ms BETWEEN 0 AND 10000", name="ck_fake_target_delay"),
    )

    # Single global mode record. The application inserts/updates row id=1.
    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, default=1, server_default=text("1"))
    status_code: Mapped[int] = mapped_column(Integer, nullable=False, default=200, server_default=text("200"))
    delay_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
