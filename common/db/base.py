from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative SQLAlchemy base used by this service.
    All database models inherit shared ORM metadata from this type.
    """
    pass
