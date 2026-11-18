from uuid import UUID

from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def create_service_base() -> type[DeclarativeBase]:
    class ServiceBase(DeclarativeBase):
        pass

    return ServiceBase


class OwnedResource:
    owner_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)


Base = create_service_base()
