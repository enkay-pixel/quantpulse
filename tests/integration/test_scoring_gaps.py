"""Scoring must fill dates that were never scored, without rewriting history.

A session ingested late — rescued by the catch-up sensor *after* that night's process run
— is never the newest feature date again. Scoring only ever looked at the newest date, so
such a session went unscored entirely: features existed, predictions did not, the paper
book carried a permanent hole, and the live track record was silently a day short.
"""

import datetime as dt
from types import SimpleNamespace

import lightgbm as lgb
import numpy as np
import pandas as pd
import pytest
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from quantpulse.data.universe import UniverseEntry, sync_universe
from quantpulse.features.engineering import FEATURE_COLUMNS, FEATURE_VERSION
from quantpulse.features.store import store_features
from quantpulse.ml import pipeline, registry
from quantpulse.ml.training import DEFAULT_PARAMS

pytestmark = pytest.mark.integration

TICKERS = ["AAA", "BBB", "CCC"]
# A late-arriving session in the middle, as happens when a rescue lands after that night's run.
DATES = [dt.date(2026, 7, 23), dt.date(2026, 7, 24), dt.date(2026, 7, 27), dt.date(2026, 7, 28)]
LATE = DATES[2]


def _frame(dates: list[dt.date]) -> pd.DataFrame:
    rng = np.random.default_rng(11)
    rows = []
    for date in dates:
        for ticker in TICKERS:
            row: dict[str, object] = {"ticker": ticker, "date": date}
            row.update(
                dict(zip(FEATURE_COLUMNS, rng.normal(size=len(FEATURE_COLUMNS)), strict=True))
            )
            rows.append(row)
    return pd.DataFrame(rows)


@pytest.fixture
def seeded(db_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> Engine:
    """Universe + features for every date, and a stub champion (version 7)."""
    with Session(db_engine) as session:
        sync_universe(session, [UniverseEntry(t, "stock") for t in TICKERS])
        session.commit()
    with Session(db_engine) as session:
        store_features(session, _frame(DATES), version=FEATURE_VERSION)
        session.commit()

    rng = np.random.default_rng(3)
    train = _frame(DATES)
    booster = lgb.train(
        {**DEFAULT_PARAMS, "seed": 1},
        lgb.Dataset(train[list(FEATURE_COLUMNS)], label=rng.normal(size=len(train))),
        num_boost_round=5,
    )
    monkeypatch.setattr(
        registry, "load_champion", lambda exchange=None: (booster, SimpleNamespace(version="7"))
    )
    return db_engine


def _scored(engine: Engine) -> dict[dt.date, set[str]]:
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT date, model_version FROM predictions")).all()
    out: dict[dt.date, set[str]] = {}
    for row in rows:
        out.setdefault(row.date, set()).add(row.model_version)
    return out


def test_a_late_session_is_scored_rather_than_skipped_forever(seeded: Engine) -> None:
    """The failure reproduced: score up to the second date, then let the third arrive late."""
    with Session(seeded) as session:
        pipeline.score_latest(seeded, session, asof=DATES[1], exchange="XNYS")
        session.commit()
    # As of 07-24 the later sessions do not exist yet, so nothing scores them.
    assert set(_scored(seeded)) == {DATES[0], DATES[1]}
    assert LATE not in _scored(seeded)

    # 07-27's ingest lands late; the next run's newest date is 07-28.
    with Session(seeded) as session:
        pipeline.score_latest(seeded, session, exchange="XNYS")
        session.commit()

    scored = _scored(seeded)
    assert LATE in scored, "the late session must be scored, not skipped forever"
    assert DATES[3] in scored
    with seeded.connect() as conn:
        filled = conn.execute(
            text("SELECT count(*) FROM predictions WHERE date = :d"), {"d": LATE}
        ).scalar_one()
    assert filled == len(TICKERS)  # the whole cross-section, not a partial fill


def test_history_is_filled_but_never_rewritten(seeded: Engine) -> None:
    """A date an earlier champion already scored must keep that champion's prediction.

    Re-scoring it would rewrite the live track record with a model that did not exist at
    the time — invisibly, because the marts take the newest model version per date.
    """
    with Session(seeded) as session:
        session.execute(
            text(
                "INSERT INTO predictions (ticker, date, model_version, score, created_at) "
                "VALUES ('AAA', :d, '1', 0.5, now())"
            ),
            {"d": DATES[0]},
        )
        session.commit()

    with Session(seeded) as session:
        pipeline.score_latest(seeded, session, exchange="XNYS")
        session.commit()

    # The old date keeps only its original champion; the new champion did not touch it.
    assert _scored(seeded)[DATES[0]] == {"1"}


def test_the_newest_date_is_always_rescored(seeded: Engine) -> None:
    """The deliberate exception: today is re-scored idempotently so a freshly promoted
    champion's view of today lands immediately rather than waiting a day."""
    with Session(seeded) as session:
        pipeline.score_latest(seeded, session, exchange="XNYS")
        session.commit()
    with Session(seeded) as session:
        session.execute(
            text("UPDATE predictions SET score = 999.0 WHERE date = :d"), {"d": DATES[3]}
        )
        session.commit()

    with Session(seeded) as session:
        pipeline.score_latest(seeded, session, exchange="XNYS")
        session.commit()

    with Session(seeded) as session:
        overwritten = session.execute(
            text("SELECT count(*) FROM predictions WHERE date = :d AND score = 999.0"),
            {"d": DATES[3]},
        ).scalar_one()
    assert overwritten == 0  # re-scored, not left stale


def test_dates_beyond_the_lookback_window_are_left_alone(
    seeded: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scoring is bounded: it fills recent holes, it does not rescore all history."""
    monkeypatch.setattr(pipeline, "SCORING_LOOKBACK_DAYS", 2)
    with Session(seeded) as session:
        pipeline.score_latest(seeded, session, exchange="XNYS")
        session.commit()
    # Window is 07-26..07-28, so the two July-23/24 dates stay unscored.
    assert set(_scored(seeded)) == {LATE, DATES[3]}


def test_no_champion_writes_nothing(seeded: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(registry, "load_champion", lambda exchange=None: None)
    with Session(seeded) as session:
        assert pipeline.score_latest(seeded, session, exchange="XNYS") == 0
        session.commit()
    assert _scored(seeded) == {}


def _run_check(engine: Engine, monkeypatch: pytest.MonkeyPatch) -> object:
    """Evaluate the asset check against the disposable test database."""
    from quantpulse.orchestration import assets

    monkeypatch.setattr(assets, "get_engine", lambda: engine)
    monkeypatch.setattr(assets, "get_session", lambda: Session(engine))
    return assets.predictions_are_current()


def test_the_check_is_blind_to_nothing_when_history_is_complete(
    seeded: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    with Session(seeded) as session:
        pipeline.score_latest(seeded, session, exchange="XNYS")
        session.commit()
    result = _run_check(seeded, monkeypatch)
    assert result.passed
    assert result.metadata["XNYS/unscored_days"].value == 0


def test_the_check_catches_a_hole_that_the_maxima_hide(
    seeded: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The blind spot: with the late date unscored but a later one scored, both maxima agree
    and a lag-only check passes while the live record is quietly a day short."""
    with Session(seeded) as session:
        pipeline.score_latest(seeded, session, exchange="XNYS")
        session.commit()
    with Session(seeded) as session:  # punch the hole a late-arriving session leaves
        session.execute(text("DELETE FROM predictions WHERE date = :d"), {"d": LATE})
        session.commit()

    result = _run_check(seeded, monkeypatch)
    assert not result.passed, "a hole between the maxima must fail the check"
    assert result.metadata["XNYS/unscored_days"].value == 1
    assert result.metadata["XNYS/lag_days"].value == 0  # lag alone would have said "fine"
    assert str(LATE) in str(result.metadata["stale"].value)


def test_the_window_widens_to_cover_a_long_outage(
    seeded: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A shutdown longer than the fixed floor must not strand the oldest sessions.

    With a 2-day floor, 07-23 and 07-24 sit outside it. They are still unscored, so the
    window has to stretch back past the floor to reach them — otherwise a fortnight away
    means a fortnight permanently missing from the books.
    """
    monkeypatch.setattr(pipeline, "SCORING_LOOKBACK_DAYS", 2)
    with Session(seeded) as session:  # one old date scored: the pre-outage state
        pipeline.score_latest(seeded, session, asof=DATES[0], exchange="XNYS")
        session.commit()

    with Session(seeded) as session:  # ...then the machine comes back days later
        pipeline.score_latest(seeded, session, exchange="XNYS")
        session.commit()

    assert set(_scored(seeded)) == set(DATES), "the whole outage must be filled, not the tail"


def test_a_fresh_database_falls_back_to_the_floor(
    seeded: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Nothing scored yet is bootstrap territory (`score --replay`), not an outage."""
    monkeypatch.setattr(pipeline, "SCORING_LOOKBACK_DAYS", 2)
    assert pipeline.last_scored_date(seeded, "XNYS") is None
    start = pipeline.scoring_window_start(seeded, "XNYS", DATES[3])
    assert start == DATES[3] - dt.timedelta(days=2)


# --- a promotion must not retroactively reclassify a day already scored ---
#
# `test_the_newest_date_is_always_rescored` above re-scores with the *same* champion, which
# is the ordinary case and is fine. The dangerous one is a champion promoted *after* the
# newest feature date: re-scoring then attributes an already-live day to a model that did
# not exist on it, and `fct_portfolio_daily` labels that 'backfilled' — so the day silently
# leaves the live track record.
#
# Reachable on a fixed schedule, not just in theory: the retrain runs Saturday and the
# process job runs Mon-Fri regardless of whether the market traded. Any Monday US holiday
# following a Saturday promotion leaves the newest feature date on Friday, before the new
# champion existed. Any Monday market holiday following a Saturday retrain does it.


def _promote(engine: Engine, version: str, on: dt.date) -> None:
    from quantpulse.db import ModelRun

    with Session(engine) as session:
        session.add(
            ModelRun(
                run_type="train",
                mlflow_run_id=f"run{version}",
                model_version=version,
                metrics={"holdout_ic": 0.03},
                decision="promoted",
                exchange="XNYS",
                created_at=dt.datetime.combine(on, dt.time(9)),
            )
        )
        session.commit()


def test_a_day_predating_the_champion_is_not_rescored_by_it(seeded: Engine) -> None:
    """The newest date keeps the champion that scored it out-of-sample.

    Champion 7 is promoted the day *after* the last feature date, so re-scoring that date
    with it would file an in-sample prediction as live evidence — and invisibly, since the
    marts take the newest model version per date.
    """
    with Session(seeded) as session:
        for ticker in TICKERS:
            session.execute(
                text(
                    "INSERT INTO predictions (ticker, date, model_version, score, created_at) "
                    "VALUES (:t, :d, '1', 0.5, now())"
                ),
                {"t": ticker, "d": DATES[3]},
            )
        session.commit()
    _promote(seeded, "1", DATES[0])
    _promote(seeded, "7", DATES[3] + dt.timedelta(days=1))  # promoted AFTER the newest date

    with Session(seeded) as session:
        pipeline.score_latest(seeded, session, exchange="XNYS")
        session.commit()

    assert _scored(seeded)[DATES[3]] == {"1"}, (
        "a champion promoted after this date must not claim it — that converts a live day "
        "into a backfilled one and shortens the out-of-sample record"
    )


def test_the_newest_date_is_still_rescored_by_a_champion_that_predates_it(
    seeded: Engine,
) -> None:
    """The documented exception has to survive the guard: in ordinary operation the
    champion was promoted before today, and today must pick up its view immediately."""
    _promote(seeded, "7", DATES[0])
    with Session(seeded) as session:
        pipeline.score_latest(seeded, session, exchange="XNYS")
        session.commit()
    assert "7" in _scored(seeded)[DATES[3]]
