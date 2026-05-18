"""A person you lay out expenses for (e.g. a parent)."""

import secrets
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def new_share_token() -> str:
    """An unguessable, URL-safe token for the public status link."""
    return secrets.token_urlsafe(24)


class Person(Base):
    __tablename__ = "person"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    # Public read-only link token. None = link disabled (revoked).
    share_token: Mapped[str | None] = mapped_column(
        String(64), unique=True, index=True, nullable=True, default=new_share_token
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    expenses: Mapped[list["Expense"]] = relationship(  # noqa: F821
        back_populates="person", cascade="all, delete-orphan"
    )
