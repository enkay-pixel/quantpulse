"""per-market drift metrics

Drift was measured across both markets pooled, which halved the signal and hid its size:
on 2026-08-10 the pooled share read 0.077 against 0.154 for either market alone, and the
worst pooled feature psi 0.21 against XJSE's 0.74.

Existing rows are stamped **POOLED** rather than assigned to a market or deleted. They are
real measurements of something — just not of either market — so calling them XNYS would
be a fabrication, and dropping them would break the append-only habit the model_runs audit
trail relies on. Queries filter by a real market code and simply will not see them.

Revision ID: f47c209a9d58
Revises: 3de6e54eece0
Create Date: 2026-08-11 13:10:26.637814

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f47c209a9d58"
down_revision: str | None = "3de6e54eece0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Not a market. Marks readings taken before drift was measured per market, so a chart of
# one market's history cannot silently splice them onto the front of its series.
LEGACY_LABEL = "POOLED"


def upgrade() -> None:
    # server_default fills the existing rows in one pass; dropping it afterwards keeps the
    # column explicit for every future insert, so a caller cannot forget the market and
    # silently get XNYS.
    op.add_column(
        "drift_metrics",
        sa.Column("exchange", sa.String(length=8), nullable=False, server_default=LEGACY_LABEL),
    )
    op.alter_column("drift_metrics", "exchange", server_default=None)
    op.create_index(op.f("ix_drift_metrics_exchange"), "drift_metrics", ["exchange"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_drift_metrics_exchange"), table_name="drift_metrics")
    op.drop_column("drift_metrics", "exchange")
