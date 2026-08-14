"""Keep the non-integration suites honestly free of a database.

Unit and Dagster tests run on synthetic data and stubs. Without enforcement a test that
quietly opens a connection finds the developer's live `market` database on localhost and
passes, then fails in CI where that database does not exist.

Pointing these suites at a dead address makes a stray query fail immediately and locally,
with a connection error naming the test, rather than silently reading production. Tests
marked `integration` are exempt, since a real database is what they are for.
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
