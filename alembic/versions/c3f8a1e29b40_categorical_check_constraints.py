"""Constrain the categorical domain columns, matching asset_type/option_type

Revision ID: c3f8a1e29b40
Revises: b7e1d9c05a42
Create Date: 2026-07-23

`universe.asset_type` and `option_quotes.option_type` already carry CHECK constraints that
document and enforce their allowed values. Three sibling columns are the same kind of
fixed, code-defined vocabulary but were left unconstrained: `prices.source`,
`model_runs.run_type`, `model_runs.decision`. This completes the pattern so the schema
tells the reader (and the database enforces) what each column may hold.

Deliberately NOT constrained here: `exchange` and `variant`. Those are config-driven
vocabularies — markets come from `data.calendar.EXCHANGES`, books from
`ml.portfolio.BOOKS`, both validated in Python. A DB CHECK would duplicate that and force a
migration every time a market or book is added, which fights the M11 design (ADR 0005).

Values verified against both the live data and the code that writes these columns before
adding the constraints.
"""

from alembic import op

revision: str = "c3f8a1e29b40"
down_revision: str | None = "b7e1d9c05a42"
branch_labels: str | None = None
depends_on: str | None = None

CONSTRAINTS = [
    # name, table, condition
    ("ck_prices_source_valid", "prices", "source IN ('yfinance', 'stooq')"),
    (
        "ck_model_runs_run_type_valid",
        "model_runs",
        "run_type IN ('train', 'promotion', 'demotion')",
    ),
    # decision is nullable (a run mid-flight has none yet); allow NULL explicitly.
    (
        "ck_model_runs_decision_valid",
        "model_runs",
        "decision IN ('promoted', 'rejected') OR decision IS NULL",
    ),
]


def upgrade() -> None:
    for name, table, condition in CONSTRAINTS:
        op.create_check_constraint(op.f(name), table, condition)


def downgrade() -> None:
    for name, table, _ in CONSTRAINTS:
        op.drop_constraint(op.f(name), table, type_="check")
