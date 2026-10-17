"""held_option_quotes: every contract the paper options book holds, every night (ADR 0008)

`option_quotes` keeps strikes within a band around spot, so a held strike the stock moved away
from dropped out of the capture. This table keeps the held contracts at any distance, apart from
`option_quotes` so the marts and completeness checks over that table read what they always have.

Revision ID: e2a4c6e8f0b2
Revises: d8f1b3c5e7a9
Create Date: 2026-10-17 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e2a4c6e8f0b2"
down_revision: str | None = "d8f1b3c5e7a9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "held_option_quotes",
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("ticker", sa.String(length=16), nullable=False),
        sa.Column("expiry", sa.Date(), nullable=False),
        sa.Column("strike", sa.Float(), nullable=False),
        sa.Column("option_type", sa.String(length=4), nullable=False),
        sa.Column("underlying_close", sa.Float(), nullable=False),
        sa.Column("bid", sa.Float(), nullable=True),
        sa.Column("ask", sa.Float(), nullable=True),
        sa.Column("last_price", sa.Float(), nullable=True),
        sa.Column("volume", sa.BigInteger(), nullable=False),
        sa.Column("open_interest", sa.BigInteger(), nullable=False),
        sa.Column("implied_volatility", sa.Float(), nullable=False),
        sa.Column("in_the_money", sa.Boolean(), nullable=False),
        sa.Column("theo_value", sa.Float(), nullable=False),
        sa.Column("delta", sa.Float(), nullable=False),
        sa.Column("gamma", sa.Float(), nullable=False),
        sa.Column("theta", sa.Float(), nullable=False),
        sa.Column("vega", sa.Float(), nullable=False),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "option_type IN ('call', 'put')",
            name=op.f("ck_held_option_quotes_held_option_type_valid"),
        ),
        sa.PrimaryKeyConstraint(
            "snapshot_date",
            "ticker",
            "expiry",
            "strike",
            "option_type",
            name=op.f("pk_held_option_quotes"),
        ),
    )


def downgrade() -> None:
    op.drop_table("held_option_quotes")
