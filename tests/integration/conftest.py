"""Integration fixtures: a disposable `market_test` database, migrated to head.

Skips cleanly when Postgres isn't reachable (e.g. `make up` not running).
"""

import os
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config as AlembicConfig
from sqlalchemy import Engine, create_engine, make_url, text
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


@pytest.fixture(autouse=True)
def _default_engine_is_the_test_db(
    test_db_url: str, monkeypatch: pytest.MonkeyPatch
) -> Iterator[None]:
    """Point every default engine at the test database for the length of an integration test.

    Code under test often reaches for `get_engine()` or `get_session()` rather than taking an
    engine, and those read DATABASE_URL — which, on a laptop with the stack's .env loaded, is the
    live database. A patch to `quantpulse.db.get_session` does not help, because modules that
    imported it by name hold their own reference. So the variable itself is redirected, as the
    unit suite does, and any path a test forgot to stub lands here rather than in production.
    """
    from quantpulse.config import get_settings
    from quantpulse.db.session import get_engine

    monkeypatch.setenv("DATABASE_URL", test_db_url)
    get_settings.cache_clear()
    get_engine.cache_clear()
    yield
    # Dispose before dropping from the cache: clearing alone abandons the pool's connections
    # still open, and the garbage collector later reports them as an error in some other test.
    for engine in (get_engine(), get_engine(None)):
        engine.dispose()
    get_settings.cache_clear()
    get_engine.cache_clear()


@pytest.fixture
def db_engine(test_db_url: str) -> Iterator[Engine]:
    engine = create_engine(test_db_url)
    # Start every test from an empty schema — the test DB is session-scoped.
    with engine.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE prices, features, predictions, model_runs, drift_metrics, "
                "portfolio_snapshots, option_quotes, pipeline_alerts, short_interest, page_views, "
                "option_book_positions, option_book_daily, held_option_quotes, watchlist, "
                "watchlist_prices, watchlist_option_quotes, "
                "universe "
                "RESTART IDENTITY CASCADE"
            )
        )
    yield engine
    # `dispose()` closes only connections that are back in the pool. One still checked out is
    # dropped instead, and when the garbage collector reaches it later it is still open — which
    # psycopg reports as a ResourceWarning from inside a destructor, under warnings-as-errors an
    # error, attributed to whichever test happens to be running when collection runs. Checking
    # here turns that into a failure of the test that leaked, at its own teardown, by name.
    leaked = engine.pool.checkedout()  # type: ignore[attr-defined]
    engine.dispose()
    assert leaked == 0, f"{leaked} connection(s) still checked out when the test finished"


def _run_dbt_build(db_url: str, select: str | None = None) -> None:
    """`dbt build` against the test database, optionally narrowed with `--select`."""
    from dbt.cli.main import dbtRunner

    transform = PROJECT_ROOT / "transform"
    url = make_url(db_url)
    env = {
        "DBT_HOST": url.host or "localhost",
        "DBT_PORT": str(url.port or 5432),
        "POSTGRES_USER": url.username or "quantpulse",
        "POSTGRES_PASSWORD": url.password or "quantpulse",
        "POSTGRES_DB": url.database or "market_test",
    }
    args = ["build", "--project-dir", str(transform), "--profiles-dir", str(transform)]
    if select:
        args += ["--select", select]
    old = {k: os.environ.get(k) for k in env}
    os.environ.update(env)
    try:
        result = dbtRunner().invoke(args)
        assert result.success, f"dbt build failed in test DB: {result.exception}"
    finally:
        for key, value in old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


@pytest.fixture(scope="session")
def dbt_build() -> Callable[..., None]:
    """Build dbt models into the test database: `dbt_build(url)` or `dbt_build(url, "+model")`."""
    return _run_dbt_build
