"""option_book_positions and option_book_daily: the paper options book (ADR 0008)

The stock signal held through spreads instead of shares. Both tables are rebuilt in full from
predictions, the share book's positions and the captured chains, so they hold no state of their
own; a skipped name is a row with its reason, so coverage gaps stay visible.

Revision ID: d8f1b3c5e7a9
Revises: c4e7a9b1d3f5
Create Date: 2026-10-17 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d8f1b3c5e7a9"
down_revision: str | None = "c4e7a9b1d3f5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "option_book_positions",
        sa.Column("book", sa.String(length=32), nullable=False),
        sa.Column("opened", sa.Date(), nullable=False),
        sa.Column("ticker", sa.String(length=16), nullable=False),
        sa.Column("exchange", sa.String(length=8), nullable=False),
        sa.Column("side", sa.String(length=8), nullable=False),
        sa.Column("phase", sa.String(length=8), nullable=False),
        sa.Column("status", sa.String(length=8), nullable=False),
        sa.Column("note", sa.String(length=200), nullable=True),
        sa.Column("option_type", sa.String(length=4), nullable=True),
        sa.Column("expiry", sa.Date(), nullable=True),
        sa.Column("long_strike", sa.Float(), nullable=True),
        sa.Column("short_strike", sa.Float(), nullable=True),
        sa.Column("entry_debit", sa.Float(), nullable=True),
        sa.Column("quantity", sa.Float(), nullable=True),
        sa.Column("mark_date", sa.Date(), nullable=True),
        sa.Column("mark_value", sa.Float(), nullable=True),
        sa.Column("mark_basis", sa.String(length=16), nullable=True),
        sa.Column("exit_date", sa.Date(), nullable=True),
        sa.Column("model_version", sa.String(length=64), nullable=True),
        sa.CheckConstraint(
            "side IN ('long', 'short')",
            name=op.f("ck_option_book_positions_option_book_side_valid"),
        ),
        sa.CheckConstraint(
            "phase IN ('replay', 'live')",
            name=op.f("ck_option_book_positions_option_book_phase_valid"),
        ),
        sa.CheckConstraint(
            "status IN ('open', 'closed', 'skipped')",
            name=op.f("ck_option_book_positions_option_book_status_valid"),
        ),
        sa.PrimaryKeyConstraint("book", "opened", "ticker", name=op.f("pk_option_book_positions")),
    )
    op.create_table(
        "option_book_daily",
        sa.Column("book", sa.String(length=32), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("exchange", sa.String(length=8), nullable=False),
        sa.Column("equity", sa.Float(), nullable=False),
        sa.Column("cash", sa.Float(), nullable=False),
        sa.Column("open_positions", sa.Integer(), nullable=False),
        sa.Column("phase", sa.String(length=8), nullable=False),
        sa.CheckConstraint(
            "phase IN ('replay', 'live')",
            name=op.f("ck_option_book_daily_option_book_daily_phase_valid"),
        ),
        sa.PrimaryKeyConstraint("book", "date", name=op.f("pk_option_book_daily")),
    )


def downgrade() -> None:
    op.drop_table("option_book_daily")
    op.drop_table("option_book_positions")
