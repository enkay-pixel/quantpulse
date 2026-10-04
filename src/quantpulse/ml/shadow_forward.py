"""Score each shadow week forward, on returns that did not exist when its candidates were fitted.

This implements the measure and the decision rule fixed in `docs/findings/shadow-run.md` before the
first shadow ran. Every constant below is a number that page committed to; changing one here is
changing the pre-registered rule, and has to be done there first, in the open.

The method, per weekly retrain and per market:

  * Refit both candidates on the panel exactly as it stood — `as_of` the production candidate's
    holdout end — and check each refit reproduces the score its week recorded. The tuned refit must
    match the production row and the fixed refit the shadow row. A refit that does not is not that
    week's model, and the week is lost rather than used: a forward score for a different model is
    not evidence about this one.
  * Score both on the next 21 sessions after the holdout, as their 21-day labels mature, with the
    same per-date rank IC the gate uses.
  * Take fixed minus tuned for the week; across weeks, the mean with a Newey-West error at lag 4,
    because each 21-session window overlaps the next four weekly ones.

The rule reads only once every week's window has matured. Until then this reports progress, and the
weeks' numbers are shown but carry no verdict.
"""

import datetime as dt
import logging
from dataclasses import dataclass
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from quantpulse.data.calendar import get_exchange
from quantpulse.db import ModelRun
from quantpulse.features.engineering import feature_columns_for
from quantpulse.ml.fixed_defaults import fixed_default, truncate_panel
from quantpulse.ml.metrics import information_coefficient, newey_west_se
from quantpulse.ml.training import TrainConfig

logger = logging.getLogger(__name__)

# --- Fixed by the pre-registration. ---------------------------------------------------------------
#: Sessions in a week's forward window: the label horizon, so not a free choice.
FORWARD_SESSIONS = 21
#: Each window overlaps the next four weekly windows.
NEWEY_WEST_LAG = 4
#: The eight weekly retrains the rule reads, by their date in New York, where the schedule runs.
WINDOW_START = dt.date(2026, 10, 10)
WINDOW_END = dt.date(2026, 11, 28)
#: Two or more lost weeks make the run not clean.
LOST_WEEKS_LIMIT = 2
ONE_SIDED_Z = 1.645
# ------------------------------------------------------------------------------------------------

#: How close a refit's holdout IC must be to the stored one to count as the same model. The fits are
#: deterministic and reproduce exactly; this only absorbs the last bits of floating point.
REPRODUCTION_TOLERANCE = 1e-9
SCHEDULE_ZONE = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class Week:
    """One market's result for one weekly retrain."""

    retrain_date: dt.date
    exchange: str
    candidate_version: str | None
    holdout_end: str | None
    #: scored | maturing | no_retrain | shadow_missing | unpaired | unrecoverable
    status: str
    forward_sessions: int
    tuned_ic: float | None
    fixed_ic: float | None
    delta: float | None
    note: str


#: Statuses that mean the week's evidence does not exist, and count against a clean run.
LOST = frozenset({"no_retrain", "shadow_missing", "unpaired", "unrecoverable"})


def saturdays(start: dt.date = WINDOW_START, end: dt.date = WINDOW_END) -> list[dt.date]:
    """The weekly retrain dates the rule reads."""
    if start.weekday() != 5 or end.weekday() != 5:
        raise ValueError("the window runs Saturday to Saturday, as the retrain schedule does")
    return [start + dt.timedelta(weeks=i) for i in range((end - start).days // 7 + 1)]


def forward_window(frame: pd.DataFrame, holdout_end: dt.date) -> tuple[pd.DataFrame, int]:
    """The first matured sessions after the holdout, up to `FORWARD_SESSIONS`, and their count.

    The panel only holds rows whose label has matured, so every date after the holdout here is one a
    21-day return can already be read for. Fewer than the full window means it is still maturing.
    """
    dates = sorted(d for d in frame["date"].unique() if d > holdout_end)[:FORWARD_SESSIONS]
    return frame[frame["date"].isin(dates)], len(dates)


def forward_ic(booster: Any, forward: pd.DataFrame) -> float:
    """Mean per-session rank IC of a model's predictions against realised returns."""
    from quantpulse.ml.registry import predict_with

    scored = forward.copy()
    scored["pred"] = predict_with(booster, scored)
    return information_coefficient(scored)


def reproduces(refit_ic: float, stored_ic: Any) -> bool:
    """Whether a refit is the model its week recorded, judged by its holdout score."""
    if stored_ic is None:
        return False
    return abs(float(refit_ic) - float(stored_ic)) <= REPRODUCTION_TOLERANCE


def weekly_pairs(
    session: Session, exchange: str, retrain_dates: list[dt.date]
) -> dict[dt.date, tuple[ModelRun | None, ModelRun | None]]:
    """For each retrain date, the production candidate and the shadow that paired with it.

    The scheduled retrain is the first `train` row of the day in New York; a drift-triggered retrain
    on a weekday is not one of the weeks the rule reads.
    """
    rows = session.scalars(
        select(ModelRun)
        .where(ModelRun.exchange == exchange, ModelRun.run_type.in_(("train", "shadow")))
        .order_by(ModelRun.id)
    ).all()
    train_by_day: dict[dt.date, ModelRun] = {}
    shadow_by_parent: dict[Any, ModelRun] = {}
    for row in rows:
        day = row.created_at.astimezone(SCHEDULE_ZONE).date()
        if row.run_type == "train":
            train_by_day.setdefault(day, row)
        else:
            shadow_by_parent.setdefault(row.metrics.get("shadows_run_id"), row)
    return {
        d: (
            train_by_day.get(d),
            shadow_by_parent.get(train_by_day[d].id) if d in train_by_day else None,
        )
        for d in retrain_dates
    }


def score_week(
    full: pd.DataFrame,
    exchange: str,
    retrain_date: dt.date,
    production: ModelRun | None,
    shadow: ModelRun | None,
    cfg: TrainConfig,
) -> Week:
    """Refit, verify and score one market's week."""
    from quantpulse.ml.training import (
        HOLDOUT_FRACTION,
        split_by_date,
        train_final_model,
        tune_hyperparameters,
    )

    def lost(status: str, note: str, version: str | None = None, end: str | None = None) -> Week:
        return Week(retrain_date, exchange, version, end, status, 0, None, None, None, note)

    if production is None:
        return lost("no_retrain", "no scheduled retrain recorded that day")
    version, end = production.model_version, production.metrics.get("holdout_end")
    if shadow is None:
        return lost("shadow_missing", "the retrain ran without its shadow", version, end)
    if not shadow.metrics.get("paired"):
        return lost("unpaired", "the shadow sat a different exam", version, end)

    market = get_exchange(exchange)
    ceiling = market.learning_rate_ceiling
    cols = feature_columns_for(exchange)
    holdout_end = dt.date.fromisoformat(str(end))
    panel = truncate_panel(full, str(end))

    train_frame, _ = split_by_date(panel, HOLDOUT_FRACTION, cfg.embargo_days)
    tuned_params = tune_hyperparameters(train_frame, cols, cfg, learning_rate_ceiling=ceiling)
    tuned, tuned_holdout = train_final_model(panel, cols, tuned_params, cfg)
    fixed, fixed_holdout = train_final_model(panel, cols, fixed_default(ceiling), cfg)
    tuned_refit = information_coefficient(tuned_holdout)
    fixed_refit = information_coefficient(fixed_holdout)
    if not reproduces(tuned_refit, production.metrics.get("holdout_ic")):
        return lost(
            "unrecoverable",
            f"tuned refit {tuned_refit:.6f} is not candidate v{version}'s "
            f"{production.metrics.get('holdout_ic')}",
            version,
            end,
        )
    if not reproduces(fixed_refit, shadow.metrics.get("holdout_ic")):
        return lost(
            "unrecoverable",
            f"fixed refit {fixed_refit:.6f} is not the shadow's {shadow.metrics.get('holdout_ic')}",
            version,
            end,
        )

    forward, n = forward_window(full, holdout_end)
    tuned_ic = forward_ic(tuned, forward) if n else None
    fixed_ic = forward_ic(fixed, forward) if n else None
    delta = (fixed_ic - tuned_ic) if tuned_ic is not None and fixed_ic is not None else None
    status = "scored" if n == FORWARD_SESSIONS else "maturing"
    note = "" if status == "scored" else f"{n} of {FORWARD_SESSIONS} sessions matured"
    return Week(retrain_date, exchange, version, end, status, n, tuned_ic, fixed_ic, delta, note)


#: The states in which the rule has been read. Scores are shown only in these.
READABLE = frozenset({"harm_shown", "no_harm_shown"})


def week_scores(week: Week, state: str) -> str:
    """A week's scores, or why they are not shown.

    Withheld until the rule can be read. Under a rule that stops the switch only on harm, a report
    that showed each week's difference as it matured would let enough looks at noise stop it — so
    before the window closes, a week shows its health and progress and nothing it could be read by.
    """
    if state in READABLE and week.delta is not None:
        return f"tuned {week.tuned_ic:+.4f} fixed {week.fixed_ic:+.4f} diff {week.delta:+.4f}"
    if week.status in {"scored", "maturing"}:
        return "scores withheld until the window closes"
    return ""


def verdict(weeks: list[Week], margin: float, expected: int) -> dict[str, Any]:
    """Apply the pre-registered rule to one market's weeks.

    `expected` is how many weekly retrains the window holds. Until all of them have happened the
    window is still open, and nothing is read however the weeks so far look.
    """
    lost = [w for w in weeks if w.status in LOST]
    if len(lost) >= LOST_WEEKS_LIMIT:
        return {
            "state": "not_clean",
            "action": f"fix the cause; the rule extends the window by {len(lost)} week(s)",
            "lost": len(lost),
        }
    if len(weeks) < expected:
        return {
            "state": "not_yet_readable",
            "action": "wait — the window's retrains have not all happened",
            "matured": sum(1 for w in weeks if w.status == "scored"),
            "of": expected,
        }
    if any(w.status == "maturing" for w in weeks):
        matured = sum(1 for w in weeks if w.status == "scored")
        return {
            "state": "not_yet_readable",
            "action": "wait — the rule reads only once every window has matured",
            "matured": matured,
            "of": len(weeks) - len(lost),
        }
    deltas = [w.delta for w in sorted(weeks, key=lambda w: w.retrain_date) if w.delta is not None]
    if len(deltas) < 2:
        return {
            "state": "not_yet_readable",
            "action": "too few scored weeks to read",
            "matured": len(deltas),
        }
    mean = sum(deltas) / len(deltas)
    se = newey_west_se(deltas, max_lag=NEWEY_WEST_LAG)
    upper = mean + ONE_SIDED_Z * se
    harm = upper < -margin
    return {
        "state": "harm_shown" if harm else "no_harm_shown",
        "action": "keep the tuner" if harm else "switch this market to fixed_default",
        "mean_delta": mean,
        "std_error": se,
        "upper_bound": upper,
        "margin": margin,
        "weeks": len(deltas),
        "lost": len(lost),
    }


def shadow_forward(
    engine: Engine, session: Session, exchange: str, cfg: TrainConfig | None = None
) -> tuple[list[Week], dict[str, Any]]:
    """Score every week in the pre-registered window for one market, and read the rule."""
    from quantpulse.ml.pipeline import build_dataset

    cfg = cfg or TrainConfig()
    dates = saturdays()
    pairs = weekly_pairs(session, exchange, dates)
    full = build_dataset(engine, cfg, exchange)
    # Today in New York, where the schedule runs — never the container's UTC date.
    today = dt.datetime.now(SCHEDULE_ZONE).date()
    weeks = [score_week(full, exchange, d, *pairs[d], cfg) for d in dates if d <= today]
    return weeks, verdict(weeks, get_exchange(exchange).ic_promotion_margin, expected=len(dates))
