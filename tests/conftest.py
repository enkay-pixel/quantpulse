"""Keep the non-integration suites honestly free of a database.

Unit and Dagster tests are supposed to run on synthetic data and stubs. Nothing enforced
that, and the failure mode is nasty: a test that quietly opens a connection finds the
developer's *live* `market` database sitting on localhost:5432 and passes, then fails in CI
where no such table exists. That is exactly how the benchmark re-ingest trigger shipped
(2026-08-13) — the sensor gained a second, unstubbed query, every local run was green, and
CI caught it only because its Postgres has no `prices` table.

So point these suites at a dead address. A stray query now fails immediately and locally,
with a connection error naming the test, instead of silently reading production. Tests
marked `integration` are exempt: a real database is the whole point of those.
"""

from collections.abc import Iterator

import pytest

from quantpulse.config import get_settings
from quantpulse.db import get_engine

# Port 1 refuses instantly rather than hanging on a connect timeout.
NOWHERE = "postgresql+psycopg://nobody:nobody@127.0.0.1:1/nodb"


@pytest.fixture(autouse=True)
def _no_database_outside_integration(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> Iterator[None]:
    if request.node.get_closest_marker("integration"):
        yield  # a bare return here yields nothing and errors every integration test
        return
    monkeypatch.setenv("DATABASE_URL", NOWHERE)
    # Both are lru_cached and read lazily, so clearing on the way in makes the override
    # take effect and clearing on the way out stops it leaking into the integration suite.
    get_settings.cache_clear()
    get_engine.cache_clear()
    yield
    get_settings.cache_clear()
    get_engine.cache_clear()
