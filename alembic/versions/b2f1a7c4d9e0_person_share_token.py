"""person share_token

Revision ID: b2f1a7c4d9e0
Revises: c0f59ada09b1
Create Date: 2026-05-18 20:30:00.000000
"""
import secrets
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b2f1a7c4d9e0"
down_revision: str | None = "c0f59ada09b1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("person", schema=None) as batch_op:
        batch_op.add_column(sa.Column("share_token", sa.String(length=64), nullable=True))

    # Backfill existing persons with a token so their link works immediately.
    bind = op.get_bind()
    person = sa.table("person", sa.column("id", sa.Integer), sa.column("share_token", sa.String))
    rows = bind.execute(sa.select(person.c.id)).fetchall()
    for (pid,) in rows:
        bind.execute(
            person.update()
            .where(person.c.id == pid)
            .values(share_token=secrets.token_urlsafe(24))
        )

    with op.batch_alter_table("person", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_person_share_token"), ["share_token"], unique=True
        )


def downgrade() -> None:
    with op.batch_alter_table("person", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_person_share_token"))
        batch_op.drop_column("share_token")
