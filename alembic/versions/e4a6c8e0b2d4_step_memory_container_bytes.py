"""step_memory.container_bytes: the container's unreclaimable memory as each step finished

The first night's estimate summed each step process's peak resident memory and came to 143% of the
daemon's cap on a night the container never reached it: forked processes share pages, which every
process's resident size counts and the container is charged once. The container's own anon +
kernel memory, read from its cgroup as each step finishes, counts them once. Nullable: rows from
before this column have no reading and are left out of the heaviest run.

Revision ID: e4a6c8e0b2d4
Revises: d2f4a6c8e0b2
Create Date: 2026-10-22 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e4a6c8e0b2d4"
down_revision: str | None = "d2f4a6c8e0b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("step_memory", sa.Column("container_bytes", sa.BigInteger(), nullable=True))


def downgrade() -> None:
    op.drop_column("step_memory", "container_bytes")
