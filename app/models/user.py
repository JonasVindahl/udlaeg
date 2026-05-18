"""User table backed by fastapi-users (UUID primary key)."""

from fastapi_users.db import SQLAlchemyBaseUserTableUUID

from app.db import Base


class User(SQLAlchemyBaseUserTableUUID, Base):
    __tablename__ = "user"
