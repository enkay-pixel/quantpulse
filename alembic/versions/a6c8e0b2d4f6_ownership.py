"""insider_transactions, holder_filings and edgar_filings: ownership from SEC EDGAR (ADR 0007)

Form 4 trades by a company's insiders, and structured Schedule 13D/13G disclosures of stakes over
5%, and a log of every filing read so none is fetched twice. Insert-only by accession number; no
foreign key to the universe, as for every research table.

Revision ID: a6c8e0b2d4f6
Revises: f4b6d8a0c2e4
Create Date: 2026-10-17 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a6c8e0b2d4f6"
down_revision: str | None = "f4b6d8a0c2e4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "insider_transactions",
        sa.Column("accession", sa.String(length=25), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("ticker", sa.String(length=16), nullable=False),
        sa.Column("form", sa.String(length=8), nullable=False),
        sa.Column("filed", sa.Date(), nullable=False),
        sa.Column("owner", sa.String(length=200), nullable=False),
        sa.Column("role", sa.String(length=200), nullable=False),
        sa.Column("planned", sa.Boolean(), nullable=True),
        sa.Column("transaction_date", sa.Date(), nullable=False),
        sa.Column("code", sa.String(length=2), nullable=False),
        sa.Column("shares", sa.Float(), nullable=False),
        sa.Column("price", sa.Float(), nullable=True),
        sa.Column("acquired", sa.String(length=1), nullable=True),
        sa.Column("shares_after", sa.Float(), nullable=True),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("accession", "seq", name=op.f("pk_insider_transactions")),
    )
    op.create_index(
        "ix_insider_transactions_ticker_date",
        "insider_transactions",
        ["ticker", "transaction_date"],
    )
    op.create_table(
        "holder_filings",
        sa.Column("accession", sa.String(length=25), nullable=False),
        sa.Column("ticker", sa.String(length=16), nullable=False),
        sa.Column("form", sa.String(length=16), nullable=False),
        sa.Column("filed", sa.Date(), nullable=False),
        sa.Column("event_date", sa.Date(), nullable=True),
        sa.Column("filer", sa.String(length=200), nullable=False),
        sa.Column("shares", sa.Float(), nullable=True),
        sa.Column("percent", sa.Float(), nullable=True),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("accession", name=op.f("pk_holder_filings")),
    )
    op.create_index("ix_holder_filings_ticker_filed", "holder_filings", ["ticker", "filed"])
    op.create_table(
        "edgar_filings",
        sa.Column("accession", sa.String(length=25), nullable=False),
        sa.Column("ticker", sa.String(length=16), nullable=False),
        sa.Column("form", sa.String(length=16), nullable=False),
        sa.Column("filed", sa.Date(), nullable=False),
        sa.Column("outcome", sa.String(length=16), nullable=False),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "outcome IN ('stored', 'other issuer', 'nothing')",
            name=op.f("ck_edgar_filings_edgar_filing_outcome_valid"),
        ),
        sa.PrimaryKeyConstraint("accession", name=op.f("pk_edgar_filings")),
    )
    op.create_index("ix_edgar_filings_ticker", "edgar_filings", ["ticker"])


def downgrade() -> None:
    op.drop_index("ix_edgar_filings_ticker", table_name="edgar_filings")
    op.drop_table("edgar_filings")
    op.drop_index("ix_holder_filings_ticker_filed", table_name="holder_filings")
    op.drop_table("holder_filings")
    op.drop_index("ix_insider_transactions_ticker_date", table_name="insider_transactions")
    op.drop_table("insider_transactions")
