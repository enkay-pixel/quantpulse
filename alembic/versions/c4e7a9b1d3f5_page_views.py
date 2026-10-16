"""page_views: daily Wikipedia attention per stock, both markets

The research branch's first table that covers the JSE (ADR 0007): neither short interest nor
option chains are published free there, but each company's Wikipedia article is. Insert-only,
with the article title stored beside each count. No foreign key to `universe`, for the same
reason as short_interest.

Revision ID: c4e7a9b1d3f5
Revises: b2d6e8f0a4c1
Create Date: 2026-10-16 23:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c4e7a9b1d3f5"
down_revision: str | None = "b2d6e8f0a4c1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "page_views",
        sa.Column("ticker", sa.String(length=16), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("article", sa.String(length=256), nullable=False),
        sa.Column("views", sa.BigInteger(), nullable=False),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("views >= 0", name=op.f("ck_page_views_views_nonnegative")),
        sa.PrimaryKeyConstraint("ticker", "date", name=op.f("pk_page_views")),
    )


def downgrade() -> None:
    op.drop_table("page_views")
