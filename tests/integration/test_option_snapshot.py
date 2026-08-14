"""`snapshot_option_chains`: the only writer of data no vendor will sell back.

It was the least-covered function on any live path (32%), which is the wrong place for
that to be true. Option chains are live-only — a day not captured is gone permanently, and
a day captured *badly* overwrites a good one, because the upsert is keyed on
`(snapshot_date, ticker, expiry, strike, option_type)`.

Its failure mode is the quiet kind this project keeps meeting: it commits per ticker and
returns a row count, so a partial snapshot returns successfully — under a third of the
universe captured, and nothing raised.

The vendor is stubbed throughout. A test that hit Yahoo would measure Yahoo.
"""

import datetime as dt
from collections.abc import Iterator
from contextlib import contextmanager

import pandas as pd
import pytest
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from quantpulse.data.universe import UniverseEntry, sync_universe
from quantpulse.options import ingest
from quantpulse.options.ingest import OffHoursSnapshotError, snapshot_option_chains

pytestmark = pytest.mark.integration

TICKERS = ["AAA", "BBB", "CCC"]
SNAP = dt.date(2026, 8, 11)
EXPIRY = SNAP + dt.timedelta(days=30)


@pytest.fixture
def factory(db_engine: Engine, monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    """Universe seeded, the clock forced post-close, and a stub chain per ticker."""
    with Session(db_engine) as session:
        sync_universe(session, [UniverseEntry(t, "stock") for t in TICKERS])
        session.commit()

    monkeypatch.setattr(ingest, "is_post_close", lambda *a, **k: True)

    def _side(kind: str) -> pd.DataFrame:
        # yfinance column names: `_rows_for_ticker` reads the vendor's frame directly.
        return pd.DataFrame(
            [
                {
                    "strike": strike,
                    "bid": 1.0,
                    "ask": 1.2,
                    "lastPrice": 1.1,
                    "volume": 10,
                    "openInterest": 100,
                    "impliedVolatility": 0.33,
                    "inTheMoney": (strike < 100.0 if kind == "call" else strike > 100.0),
                }
                for strike in (95.0, 100.0, 105.0)
            ]
        )

    def fake_chain(ticker: str, n_expiries: int):  # type: ignore[no-untyped-def]
        return 100.0, [(EXPIRY, _side("call"), _side("put"))]

    monkeypatch.setattr(ingest, "_fetch_ticker_chain", fake_chain)

    @contextmanager
    def make_session() -> Iterator[Session]:
        with Session(db_engine) as s:
            yield s
            s.commit()

    return make_session, db_engine


def _rows(engine: Engine) -> dict[str, int]:
    with engine.connect() as conn:
        return {
            r.ticker: r.n
            for r in conn.execute(
                text("SELECT ticker, count(*) AS n FROM option_quotes GROUP BY ticker")
            )
        }


def test_a_full_snapshot_covers_every_ticker(factory) -> None:  # type: ignore[no-untyped-def]
    make_session, engine = factory
    written = snapshot_option_chains(make_session, TICKERS, snapshot_date=SNAP)
    assert written > 0
    assert set(_rows(engine)) == set(TICKERS)


def test_one_failing_ticker_does_not_lose_the_others(
    factory, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    """The reason it commits per ticker. A vendor erroring on one name must cost that
    name only — the alternative is one bad symbol discarding a ten-minute capture."""
    make_session, engine = factory
    real = ingest._fetch_ticker_chain

    def flaky(ticker: str, n: int):  # type: ignore[no-untyped-def]
        if ticker == "BBB":
            raise RuntimeError("vendor exploded")
        return real(ticker, n)

    monkeypatch.setattr(ingest, "_fetch_ticker_chain", flaky)

    snapshot_option_chains(make_session, TICKERS, snapshot_date=SNAP)
    assert set(_rows(engine)) == {"AAA", "CCC"}


def test_a_ticker_with_no_chain_is_skipped_not_written_empty(
    factory, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    make_session, engine = factory
    real = ingest._fetch_ticker_chain
    monkeypatch.setattr(
        ingest,
        "_fetch_ticker_chain",
        lambda t, n: (None, []) if t == "CCC" else real(t, n),
    )

    snapshot_option_chains(make_session, TICKERS, snapshot_date=SNAP)
    assert "CCC" not in _rows(engine)


def test_a_partial_snapshot_still_reports_success(factory, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Documenting the sharp edge rather than pretending it is not there: two tickers of
    three returns a positive count and raises nothing. That is deliberate — the run is
    resumable — but it is why `option_snapshot_quality` exists to judge coverage, and why
    the repair sensor re-runs a thin day. A caller must never read "wrote N rows" as
    "captured the universe"."""
    make_session, engine = factory
    real = ingest._fetch_ticker_chain
    monkeypatch.setattr(
        ingest,
        "_fetch_ticker_chain",
        lambda t, n: (_ for _ in ()).throw(RuntimeError("down")) if t == "AAA" else real(t, n),
    )

    written = snapshot_option_chains(make_session, TICKERS, snapshot_date=SNAP)
    assert written > 0  # success-looking
    assert len(_rows(engine)) == 2  # ...on an incomplete universe


def test_rerunning_the_same_day_updates_rather_than_duplicates(factory) -> None:  # type: ignore[no-untyped-def]
    """A thin day gets re-run by the repair sensor. The upsert key must absorb the second
    pass, or the table doubles and every coverage figure lies."""
    make_session, engine = factory
    snapshot_option_chains(make_session, TICKERS, snapshot_date=SNAP)
    first = _rows(engine)
    snapshot_option_chains(make_session, TICKERS, snapshot_date=SNAP)
    assert _rows(engine) == first


def test_off_hours_snapshots_are_refused(factory, monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[no-untyped-def]
    """The gate that matters most. Pre-market IV is ~2% against ~33% post-close, and the
    upsert would overwrite good post-close rows for every ticker it reached — one
    snapshot_date holding two incompatible qualities of data, unrebuildable."""
    make_session, engine = factory
    monkeypatch.setattr(ingest, "is_post_close", lambda *a, **k: False)

    with pytest.raises(OffHoursSnapshotError, match="before the close"):
        snapshot_option_chains(make_session, TICKERS, snapshot_date=SNAP)
    assert _rows(engine) == {}, "nothing may be written when the gate refuses"


def test_force_exists_for_testing_and_bypasses_the_gate(
    factory, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    make_session, engine = factory
    monkeypatch.setattr(ingest, "is_post_close", lambda *a, **k: False)

    snapshot_option_chains(make_session, TICKERS, snapshot_date=SNAP, force=True)
    assert set(_rows(engine)) == set(TICKERS)


def test_the_stamped_date_is_the_exchange_date(factory, monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[no-untyped-def]
    """Containers run UTC. Defaulting to `date.today()` would stamp rows a day forward
    every evening under EST and shift the whole options history at the DST change —
    invisibly, in a dataset that cannot be rebuilt."""
    make_session, engine = factory
    monkeypatch.setattr(ingest, "market_today", lambda *a, **k: dt.date(2026, 8, 12))

    snapshot_option_chains(make_session, TICKERS)
    with engine.connect() as conn:
        dates = {
            r[0] for r in conn.execute(text("SELECT DISTINCT snapshot_date FROM option_quotes"))
        }
    assert dates == {dt.date(2026, 8, 12)}
