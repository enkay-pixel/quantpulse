"""Make exchange a first-class dimension

Revision ID: b7e1d9c05a42
Revises: a1c4f2b9d3e7
Create Date: 2026-07-23

Only three tables need it. `universe` is the source of truth; `portfolio_snapshots` and
`model_runs` are per-market aggregates with no ticker to join through. `prices`, `features`
and `predictions` stay untouched — tickers are globally unique (JSE carries a `.JO` suffix),
so they reach exchange by joining `universe`, which avoids denormalisation drift.

Everything existing is NYSE, so the default backfills correctly.
"""

import sqlalchemy as sa
from alembic import op

revision: str = "b7e1d9c05a42"
down_revision: str | None = "a1c4f2b9d3e7"
branch_labels: str | None = None
depends_on: str | None = None

PK = "pk_portfolio_snapshots"  # db.base.NAMING_CONVENTION, not Postgres' default


def upgrade() -> None:
    for table in ("universe", "portfolio_snapshots", "model_runs"):
        op.add_column(
            table,
            sa.Column("exchange", sa.String(8), nullable=False, server_default="XNYS"),
        )

    # A book is per (date, exchange, variant): two markets rebalance on the same date.
    op.drop_constraint(PK, "portfolio_snapshots", type_="primary")
    op.create_primary_key(PK, "portfolio_snapshots", ["date", "exchange", "variant"])

    op.create_index("ix_universe_exchange", "universe", ["exchange"])


def downgrade() -> None:
    op.drop_index("ix_universe_exchange", table_name="universe")
    op.drop_constraint(PK, "portfolio_snapshots", type_="primary")
    # Only NYSE rows fit a key without exchange.
    op.execute("DELETE FROM portfolio_snapshots WHERE exchange <> 'XNYS'")
    op.create_primary_key(PK, "portfolio_snapshots", ["date", "variant"])
    for table in ("universe", "portfolio_snapshots", "model_runs"):
        op.drop_column(table, "exchange")
