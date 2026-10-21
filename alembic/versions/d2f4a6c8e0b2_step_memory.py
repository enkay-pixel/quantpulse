"""step_memory: each Dagster step's peak memory, for the daemon's headroom check

The daemon container's cap is shared by the daemon, its code server, each run's worker and the
run's step processes, and the cgroup counts page cache against it too, so reaching the cap says
little on its own. A hook records every finished step's peak resident memory here; the resource
report sums the steps that overlapped to estimate the heaviest run.

Revision ID: d2f4a6c8e0b2
Revises: c0e2a4b6d8f0
Create Date: 2026-10-21 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d2f4a6c8e0b2"
down_revision: str | None = "c0e2a4b6d8f0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "step_memory",
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("step_key", sa.String(length=255), nullable=False),
        sa.Column("job_name", sa.String(length=64), nullable=False),
        sa.Column("pid", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("peak_rss_bytes", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint("run_id", "step_key", name=op.f("pk_step_memory")),
    )
    op.create_index(
        op.f("ix_step_memory_finished_at"), "step_memory", ["finished_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_step_memory_finished_at"), table_name="step_memory")
    op.drop_table("step_memory")
