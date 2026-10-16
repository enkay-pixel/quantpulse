"""One answer to "is the data whole, and what comes next?", read from the stored record.

Each check-in used to rebuild this from a dozen queries, by hand, and a query written in a hurry
is the kind that is quietly wrong or slow. This holds them in one place: freshness per market,
the recent sessions and any tickers they are missing, the champion and its streak, the shadow
run's progress, and the dates ahead. Read-only, and quick enough to run at any time.
"""

import datetime as dt
from dataclasses import dataclass, field

from sqlalchemy import text
from sqlalchemy.engine import Engine

from quantpulse.data.calendar import (
    NEW_YORK,
    is_trading_day,
    last_trading_day,
    market_today,
    trading_days,
)

RECENT_SESSIONS = 5


@dataclass(frozen=True)
class Session:
    day: dt.date
    covered: int
    universe: int
    missing: tuple[str, ...] = ()


@dataclass(frozen=True)
class MarketStatus:
    exchange: str
    expected: dt.date
    prices: dt.date | None
    features: dt.date | None
    predictions: dt.date | None
    predictions_version: str | None
    recent: tuple[Session, ...]
    champion: str | None
    champion_since: dt.date | None
    rejections: int
    shadow_recorded: int
    shadow_due: int
    shadow_in_window: int
    trained_through: dt.date | None = None
    notes: tuple[str, ...] = field(default_factory=tuple)


def expected_session(exchange: str) -> dt.date:
    """The newest session whose scheduled ingest has already had its turn."""
    from quantpulse.orchestration.catchup import ingest_overdue

    today = market_today(exchange)
    if is_trading_day(today, exchange) and ingest_overdue(exchange=exchange):
        return today
    return last_trading_day(today - dt.timedelta(days=1), exchange)


def market_status(engine: Engine, exchange: str) -> MarketStatus:
    from quantpulse.ml.shadow_forward import SCHEDULE_ZONE, due, saturdays
    from quantpulse.orchestration.catchup import latest_training_day, missing_tickers

    params = {"ex": exchange}
    with engine.connect() as conn:
        prices = conn.execute(
            text(
                "SELECT max(p.date) FROM prices p JOIN universe u USING (ticker) "
                "WHERE u.exchange = :ex"
            ),
            params,
        ).scalar()
        features = conn.execute(
            text(
                "SELECT max(f.date) FROM features f JOIN universe u USING (ticker) "
                "WHERE u.exchange = :ex"
            ),
            params,
        ).scalar()
        pred = conn.execute(
            text(
                "SELECT p.date, max(p.model_version) FROM predictions p JOIN universe u "
                "USING (ticker) WHERE u.exchange = :ex GROUP BY p.date ORDER BY p.date DESC LIMIT 1"
            ),
            params,
        ).first()
        universe: int = conn.execute(
            text("SELECT count(*) FROM universe WHERE active AND exchange = :ex"), params
        ).scalar_one()
        recent_rows = conn.execute(
            text(
                "SELECT p.date, count(*) FROM prices p JOIN universe u USING (ticker) "
                "WHERE u.exchange = :ex GROUP BY p.date ORDER BY p.date DESC LIMIT :n"
            ),
            {**params, "n": RECENT_SESSIONS},
        ).all()
        # The champion is the newest promotion not withdrawn afterwards by a demotion.
        champ = conn.execute(
            text(
                """
                SELECT m.model_version, m.created_at FROM model_runs m
                WHERE m.exchange = :ex AND m.run_type = 'train' AND m.decision = 'promoted'
                  AND NOT EXISTS (
                      SELECT 1 FROM model_runs d
                      WHERE d.run_type = 'demotion' AND d.exchange = m.exchange
                        AND d.model_version = m.model_version AND d.created_at > m.created_at)
                ORDER BY m.created_at DESC LIMIT 1
                """
            ),
            params,
        ).first()
        rejections: int = conn.execute(
            text(
                "SELECT count(*) FROM model_runs WHERE exchange = :ex AND run_type = 'train' "
                "AND decision = 'rejected' AND (CAST(:since AS timestamptz) IS NULL "
                "OR created_at > CAST(:since AS timestamptz))"
            ),
            {**params, "since": champ.created_at if champ else None},
        ).scalar_one()
        shadows = conn.execute(
            text(
                "SELECT created_at FROM model_runs WHERE exchange = :ex AND run_type = 'shadow' "
                "AND (metrics->>'paired')::boolean"
            ),
            params,
        ).all()

    recent = []
    for row in sorted(recent_rows, key=lambda r: r[0]):
        day: dt.date = row[0]
        covered = int(row[1])
        gaps = tuple(missing_tickers(day, exchange)) if covered < universe else ()
        recent.append(Session(day, covered, int(universe), gaps))

    window = saturdays()
    shadow_due = due(window, dt.datetime.now(SCHEDULE_ZONE).date())
    shadow_days = {r.created_at.astimezone(SCHEDULE_ZONE).date() for r in shadows}
    return MarketStatus(
        exchange=exchange,
        expected=expected_session(exchange),
        prices=prices,
        features=features,
        predictions=pred[0] if pred else None,
        predictions_version=str(pred[1]) if pred else None,
        recent=tuple(recent),
        champion=str(champ.model_version) if champ else None,
        champion_since=champ.created_at.astimezone(NEW_YORK).date() if champ else None,
        rejections=int(rejections),
        shadow_recorded=sum(1 for d in shadow_due if d in shadow_days),
        shadow_due=len(shadow_due),
        shadow_in_window=len(window),
        trained_through=latest_training_day(exchange),
    )


def sessions_ahead(start: dt.date, n: int, exchange: str) -> dt.date:
    """The date of the `n`-th session after `start` on this market's calendar."""
    days = trading_days(
        start + dt.timedelta(days=1), start + dt.timedelta(days=2 * n + 30), exchange
    )
    return days[n - 1]


def live_sessions_reached(end_date: dt.date, have: int, need: int, exchange: str) -> dt.date:
    """The session whose close brings the live record to `need` sessions.

    Not the date of the `need`-th session itself: a day's return is realized at the next close,
    so the live record ends one session behind the prices, and a count of `need` is first
    readable once the session after it has closed — that evening's ingest, and the decisions job
    the next weekday morning. Dating the milestone by its own session put it a day or more early.
    """
    return sessions_ahead(end_date, need - have + 1, exchange)


def next_retrain(today: dt.date | None = None) -> dt.date:
    """The next scheduled retrain: Saturdays, on the New York calendar — today, on a Saturday."""
    today = today or dt.datetime.now(NEW_YORK).date()
    return today + dt.timedelta(days=(5 - today.weekday()) % 7)


def shadow_verdict_eta() -> dt.date:
    """When the shadow run's last forward window matures, so the rule can first be read.

    The last retrain in the window fits on data ending the session before it; its forward window
    is the 21 sessions after its holdout, which ends that same session; and those labels need a
    further 21 sessions to mature.
    """
    from quantpulse.ml.shadow_forward import FORWARD_SESSIONS, WINDOW_END

    data_end = last_trading_day(WINDOW_END - dt.timedelta(days=1), "XNYS")
    return sessions_ahead(data_end, FORWARD_SESSIONS, "XNYS")
