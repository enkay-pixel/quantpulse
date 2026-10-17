"""financial_facts and fundamentals_fetches: company fundamentals from SEC EDGAR (ADR 0007)

Revenue, earnings, cash flow and balance-sheet figures from each 10-K and 10-Q, kept as reported
and keyed by filing, so a restated figure sits beside the original. Insert-only; no foreign key to
the universe, as for every research table. fundamentals_fetches records when each company was
last fetched, so a statement EDGAR's facts document has not caught up with is retried weekly.

Revision ID: c0e2a4b6d8f0
Revises: b8d0f2a4c6e8
Create Date: 2026-10-17 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c0e2a4b6d8f0"
down_revision: str | None = "b8d0f2a4c6e8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "financial_facts",
        sa.Column("ticker", sa.String(length=16), nullable=False),
        sa.Column("concept", sa.String(length=100), nullable=False),
        sa.Column("unit", sa.String(length=16), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("duration_days", sa.Integer(), nullable=False),
        sa.Column("accession", sa.String(length=25), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=True),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("fiscal_year", sa.Integer(), nullable=True),
        sa.Column("fiscal_period", sa.String(length=4), nullable=True),
        sa.Column("form", sa.String(length=8), nullable=False),
        sa.Column("filed", sa.Date(), nullable=False),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint(
            "ticker",
            "concept",
            "unit",
            "period_end",
            "duration_days",
            "accession",
            name=op.f("pk_financial_facts"),
        ),
    )
    op.create_index("ix_financial_facts_ticker_concept", "financial_facts", ["ticker", "concept"])
    op.create_table(
        "fundamentals_fetches",
        sa.Column("ticker", sa.String(length=16), nullable=False),
        sa.Column("newest_statement", sa.String(length=25), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("ticker", name=op.f("pk_fundamentals_fetches")),
    )


def downgrade() -> None:
    op.drop_table("fundamentals_fetches")
    op.drop_index("ix_financial_facts_ticker_concept", table_name="financial_facts")
    op.drop_table("financial_facts")
