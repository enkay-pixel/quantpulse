"""short_interest, the research branch's first table

Shares sold short per ticker and settlement date (ADR 0007). Insert-only, so `ingested_at` is
when a figure was first seen — the date history is keyed by, since short interest reaches the
vendor a week or two after it settles. No foreign key to `universe`: research tickers must be
addable without entering the model's training universe.

Revision ID: b2d6e8f0a4c1
Revises: e8b4f1a6c2d9
Create Date: 2026-10-16 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b2d6e8f0a4c1"
down_revision: str | None = "e8b4f1a6c2d9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "short_interest",
        sa.Column("ticker", sa.String(length=16), nullable=False),
        sa.Column("settlement_date", sa.Date(), nullable=False),
        sa.Column("shares_short", sa.BigInteger(), nullable=False),
        sa.Column("shares_short_prior", sa.BigInteger(), nullable=True),
        sa.Column("prior_settlement_date", sa.Date(), nullable=True),
        sa.Column("short_pct_float", sa.Float(), nullable=True),
        sa.Column("days_to_cover", sa.Float(), nullable=True),
        sa.Column("float_shares", sa.BigInteger(), nullable=True),
        sa.Column("shares_outstanding", sa.BigInteger(), nullable=True),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "shares_short >= 0", name=op.f("ck_short_interest_shares_short_nonnegative")
        ),
        sa.CheckConstraint(
            "source IN ('yfinance')", name=op.f("ck_short_interest_short_interest_source_valid")
        ),
        sa.PrimaryKeyConstraint("ticker", "settlement_date", name=op.f("pk_short_interest")),
    )


def downgrade() -> None:
    op.drop_table("short_interest")
