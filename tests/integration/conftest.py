"""Integration fixtures: a disposable `market_test` database, migrated to head.

Skips cleanly when Postgres isn't reachable (e.g. `make up` not running).
"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config as AlembicConfig
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import OperationalError

from quantpulse.config import Settings

PROJECT_ROOT = Path(__file__).parents[2]
TEST_DB = "market_test"


@pytest.fixture(scope="session")
def test_db_url() -> Iterator[str]:
    base_url = Settings(_env_file=PROJECT_ROOT / ".env").database_url
    admin = create_engine(base_url, isolation_level="AUTOCOMMIT", pool_pre_ping=True)
    try:
        with admin.connect() as conn:
            conn.execute(text(f"DROP DATABASE IF EXISTS {TEST_DB} WITH (FORCE)"))
            conn.execute(text(f"CREATE DATABASE {TEST_DB}"))
    except OperationalError:
        pytest.skip("Postgres not reachable — start it with `make up`")

    url = base_url.rsplit("/", 1)[0] + f"/{TEST_DB}"
    cfg = AlembicConfig(str(PROJECT_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")

    yield url

    with admin.connect() as conn:
        conn.execute(text(f"DROP DATABASE IF EXISTS {TEST_DB} WITH (FORCE)"))
    admin.dispose()


@pytest.fixture
def db_engine(test_db_url: str) -> Iterator[Engine]:
    engine = create_engine(test_db_url)
    yield engine
    engine.dispose()
