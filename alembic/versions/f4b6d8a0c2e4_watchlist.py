"""watchlist, watchlist_prices and watchlist_option_quotes: the research watchlist (ADR 0007)

Names the research branch follows that the model does not. They get their own bars and chains, in
tables with no foreign key to the universe, so nothing here can reach a model input.

Revision ID: f4b6d8a0c2e4
Revises: e2a4c6e8f0b2
Create Date: 2026-10-17 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f4b6d8a0c2e4"
down_revision: str | None = "e2a4c6e8f0b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "watchlist",
        sa.Column("ticker", sa.String(length=16), nullable=False),
        sa.Column("exchange", sa.String(length=8), nullable=False),
        sa.Column("asset_type", sa.String(length=8), nullable=False),
        sa.Column("why", sa.String(length=300), nullable=False),
        sa.Column("wikipedia", sa.String(length=200), nullable=True),
        sa.Column(
            "added_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "asset_type IN ('stock', 'etf')",
            name=op.f("ck_watchlist_watchlist_asset_type_valid"),
        ),
        sa.PrimaryKeyConstraint("ticker", name=op.f("pk_watchlist")),
    )
    op.create_table(
        "watchlist_prices",
        sa.Column("ticker", sa.String(length=16), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("open", sa.Float(), nullable=False),
        sa.Column("high", sa.Float(), nullable=False),
        sa.Column("low", sa.Float(), nullable=False),
        sa.Column("close", sa.Float(), nullable=False),
        sa.Column("volume", sa.BigInteger(), nullable=False),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "close > 0 AND open > 0 AND high > 0 AND low > 0",
            name=op.f("ck_watchlist_prices_watchlist_prices_positive"),
        ),
        sa.CheckConstraint("high >= low", name=op.f("ck_watchlist_prices_watchlist_high_gte_low")),
        sa.PrimaryKeyConstraint("ticker", "date", name=op.f("pk_watchlist_prices")),
    )
    op.create_table(
        "watchlist_option_quotes",
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
            name=op.f("ck_watchlist_option_quotes_watchlist_option_type_valid"),
        ),
        sa.PrimaryKeyConstraint(
            "snapshot_date",
            "ticker",
            "expiry",
            "strike",
            "option_type",
            name=op.f("pk_watchlist_option_quotes"),
        ),
    )


def downgrade() -> None:
    op.drop_table("watchlist_option_quotes")
    op.drop_table("watchlist_prices")
    op.drop_table("watchlist")
