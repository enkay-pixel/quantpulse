"""Foreign-key every ticker column to universe, matching prices

Revision ID: d5a2c9f18e63
Revises: c3f8a1e29b40
Create Date: 2026-07-23

`prices.ticker` already references `universe.ticker` (ON DELETE RESTRICT). `features`,
`predictions` and `option_quotes` reference the same tickers but carried no such
constraint — an inconsistency in the schema's story. Every ticker in these tables comes
from `active_tickers(universe)`, and `sync_universe` deactivates rather than deletes, so
the constraint is always satisfiable and RESTRICT never fires in normal operation; it just
makes the relationship the queries already assume explicit and enforced.

ON DELETE RESTRICT (not CASCADE): a universe row is never deleted in this system, and if it
somehow were, silently dropping its price/feature/prediction history is the wrong default.
"""

from alembic import op

revision: str = "d5a2c9f18e63"
down_revision: str | None = "c3f8a1e29b40"
branch_labels: str | None = None
depends_on: str | None = None

# (constraint name, source table)
FOREIGN_KEYS = [
    ("fk_features_ticker_universe", "features"),
    ("fk_predictions_ticker_universe", "predictions"),
    ("fk_option_quotes_ticker_universe", "option_quotes"),
]


def upgrade() -> None:
    for name, table in FOREIGN_KEYS:
        op.create_foreign_key(
            op.f(name), table, "universe", ["ticker"], ["ticker"], ondelete="RESTRICT"
        )


def downgrade() -> None:
    for name, table in FOREIGN_KEYS:
        op.drop_constraint(op.f(name), table, type_="foreignkey")
