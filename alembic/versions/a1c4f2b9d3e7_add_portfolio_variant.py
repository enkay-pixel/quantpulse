"""Add variant to portfolio_snapshots so several books can coexist

Revision ID: a1c4f2b9d3e7
Revises: 80ed0da02bb9
Create Date: 2026-07-22

The paper book rebalances daily; the model forecasts 21 trading days ahead. Rather
than picking one, both are stored side by side and keyed by `variant`, so the
difference between them is measurable instead of confounded.
"""

import sqlalchemy as sa
from alembic import op

revision: str = "a1c4f2b9d3e7"
down_revision: str | None = "80ed0da02bb9"
branch_labels: str | None = None
depends_on: str | None = None

# Follows db.base.NAMING_CONVENTION ("pk_%(table_name)s"), not Postgres' default
# "<table>_pkey" — the convention is what actually created this constraint.
PK_NAME = "pk_portfolio_snapshots"


def upgrade() -> None:
    op.add_column(
        "portfolio_snapshots",
        sa.Column("variant", sa.String(16), nullable=False, server_default="daily"),
    )
    op.drop_constraint(PK_NAME, "portfolio_snapshots", type_="primary")
    op.create_primary_key(PK_NAME, "portfolio_snapshots", ["date", "variant"])


def downgrade() -> None:
    op.drop_constraint(PK_NAME, "portfolio_snapshots", type_="primary")
    # Only the daily book fits a date-only key; the rest cannot be represented.
    op.execute("DELETE FROM portfolio_snapshots WHERE variant <> 'daily'")
    op.create_primary_key(PK_NAME, "portfolio_snapshots", ["date"])
    op.drop_column("portfolio_snapshots", "variant")
