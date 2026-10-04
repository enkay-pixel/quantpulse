"""shadow run type, which can never carry a decision

A shadow is a configuration fitted beside the weekly candidate for comparison only — never
registered, never gated, never champion. It gets its own run_type so that every reader which
already selects `run_type = 'train'` passes over it without being changed.

That is not enough on its own. The live record's start date and the backfilled boundary both
identify champions by `decision = 'promoted'` without consulting run_type, so a shadow row
carrying a decision would be read as a promotion by both. The second constraint makes that
impossible in the table itself rather than leaving it to the code that writes the rows.

Revision ID: e8b4f1a6c2d9
Revises: f47c209a9d58
Create Date: 2026-10-04 14:30:00.000000

"""

from collections.abc import Sequence

from alembic import op

revision: str = "e8b4f1a6c2d9"
down_revision: str | None = "f47c209a9d58"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(op.f("ck_model_runs_run_type_valid"), "model_runs", type_="check")
    op.create_check_constraint(
        op.f("ck_model_runs_run_type_valid"),
        "model_runs",
        "run_type IN ('train', 'promotion', 'demotion', 'shadow')",
    )
    op.create_check_constraint(
        op.f("ck_model_runs_shadow_never_decides"),
        "model_runs",
        "run_type <> 'shadow' OR decision IS NULL",
    )


def downgrade() -> None:
    # Refuses while shadow rows exist, because the narrower constraint would reject them. That
    # is the right failure: deleting audit rows to make a downgrade succeed is not a decision for
    # a migration to take on its own.
    op.drop_constraint(op.f("ck_model_runs_shadow_never_decides"), "model_runs", type_="check")
    op.drop_constraint(op.f("ck_model_runs_run_type_valid"), "model_runs", type_="check")
    op.create_check_constraint(
        op.f("ck_model_runs_run_type_valid"),
        "model_runs",
        "run_type IN ('train', 'promotion', 'demotion')",
    )
