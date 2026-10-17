"""holder_filings.share_class: which class of stock a stake over 5% is in (ADR 0007)

A company with several classes is filed on per class: Berkshire's largest holder reports 38% of
Class A, not of the Class B shares the universe tracks. Without the class, the percentage reads as
a stake in the wrong shares. Nullable: rows stored before it are filled by the next fetch.

Revision ID: b8d0f2a4c6e8
Revises: a6c8e0b2d4f6
Create Date: 2026-10-17 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b8d0f2a4c6e8"
down_revision: str | None = "a6c8e0b2d4f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("holder_filings", sa.Column("share_class", sa.String(length=200), nullable=True))


def downgrade() -> None:
    op.drop_column("holder_filings", "share_class")
