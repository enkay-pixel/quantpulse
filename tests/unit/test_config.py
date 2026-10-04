from quantpulse.config import Settings


def test_settings_defaults() -> None:
    s = Settings(_env_file=None)
    assert s.database_url.startswith("postgresql+psycopg://")
    assert s.api_port == 8000


def test_settings_env_override(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@db:5432/market")
    s = Settings(_env_file=None)
    assert s.database_url == "postgresql+psycopg://u:p@db:5432/market"


def test_every_database_url_names_its_driver() -> None:
    """A bare `postgresql://` lets SQLAlchemy choose the driver, and it changes its mind.

    SQLAlchemy 2.0 resolves a bare scheme to psycopg2; 2.1 resolves it to psycopg 3. The Dagster
    storage URL was bare, so a dependency bump silently moved Dagster to a driver it was not built
    against — most paths kept working, the webserver's index page failed on a closed connection,
    and nothing in the project had changed. Naming the driver makes the choice ours and makes a
    version bump unable to make it for us.
    """
    import pathlib
    import re

    root = pathlib.Path(__file__).resolve().parents[2]
    sources = ["docker-compose.yml", ".env.example", "src/quantpulse/config.py", "alembic.ini"]
    scheme = re.compile(r"postgres(?:ql)?(\+[A-Za-z0-9_]+)?://")
    found = []
    for rel in sources:
        path = root / rel
        if not path.exists():
            continue
        for lineno, line in enumerate(path.read_text().splitlines(), 1):
            for match in scheme.finditer(line):
                found.append((rel, lineno, match.group(0), match.group(1)))
    # The check must actually be looking at something, or it passes by scanning nothing.
    assert found, "no database URLs found — the scan is not reading the files it should"
    bare = [f"{rel}:{lineno} {url}" for rel, lineno, url, driver in found if not driver]
    assert not bare, "database URLs without an explicit driver: " + ", ".join(bare)
