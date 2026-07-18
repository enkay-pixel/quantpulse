"""Dependency-injected DB access so tests can point the app at a throwaway database."""

from collections.abc import Iterator

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from quantpulse.db import get_engine


def engine_dep() -> Engine:
    return get_engine()


def session_dep() -> Iterator[Session]:
    with Session(get_engine()) as session:
        yield session
