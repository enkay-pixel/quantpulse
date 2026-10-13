"""Running the migrations must not silence the application's loggers.

Alembic's env.py configures logging from alembic.ini, and `fileConfig` disables every logger that
already exists unless told otherwise. Any process that migrates in-process — `quantpulse init-db`,
or this suite's own fixtures — then loses the log output of every module imported before the
migration, without an error. In the suite that showed up as a test reading an empty log; in the CLI
it drops the line confirming the migration ran.
"""

import pytest

from quantpulse.data import ingest

pytestmark = pytest.mark.integration


def test_a_logger_created_before_migrating_still_logs(test_db_url: str) -> None:
    # `test_db_url` has migrated the test database by the time this runs, and `ingest` was
    # imported at collection, before that.
    assert not ingest.logger.disabled, "migrating disabled a logger that already existed"
