"""Standing decisions, and whether anything has reopened one.

`configs/decisions.yaml` lists each standing decision with the conditions that would reopen it —
the "reopen when" clauses of the roadmap, written as data. Kept only as prose, those clauses are
remembered by whoever happens to reread the roadmap. This evaluates them against the stored
record and says which condition fired and on what figure. Whether to change the decision stays
the owner's call: nothing here acts.
"""

import datetime as dt
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import text
from sqlalchemy.engine import Engine

from quantpulse.data.calendar import get_exchange

#: |t| at which a live alpha counts as resolved, either way.
ALPHA_T_RESOLVES = 2.0


@dataclass(frozen=True)
class Live:
    sessions: int
    sharpe: float | None
    alpha_t: float | None
    end_date: dt.date | None


@dataclass(frozen=True)
class Snapshot:
    """The figures the conditions are judged on."""

    live: dict[str, Live]
    promotions: dict[str, list[dt.date]]
    option_snapshot_days: int
    #: Markets with a saved shadow verdict, or None when the verdict directory cannot be seen
    #: from where this runs — which is "unknown", not "none saved".
    verdicts: frozenset[str] | None


@dataclass(frozen=True)
class Condition:
    type: str
    params: dict[str, Any]


@dataclass(frozen=True)
class Decision:
    id: str
    title: str
    decided: dt.date
    conditions: tuple[Condition, ...]
    note: str | None = None


@dataclass(frozen=True)
class Outcome:
    decision: Decision
    condition: Condition
    #: fired | armed | unknown | manual
    state: str
    detail: str


Evaluator = Callable[[Condition, Decision, Snapshot], tuple[str, str]]


def _live(c: Condition, s: Snapshot) -> Live | None:
    return s.live.get(c.params["exchange"])


def _live_sessions_at_least(c: Condition, d: Decision, s: Snapshot) -> tuple[str, str]:
    ex, need = c.params["exchange"], int(c.params["sessions"])
    live = _live(c, s)
    if live is None:
        return "unknown", f"no {ex} live record"
    state = "fired" if live.sessions >= need else "armed"
    return state, f"{ex} live sessions {live.sessions} of {need}"


def _live_sharpe_below(c: Condition, d: Decision, s: Snapshot) -> tuple[str, str]:
    ex, value = c.params["exchange"], float(c.params["value"])
    live = _live(c, s)
    if live is None or live.sharpe is None:
        return "unknown", f"no {ex} live Sharpe"
    state = "fired" if live.sharpe < value else "armed"
    return state, f"{ex} live Sharpe {live.sharpe:+.2f} (reopens below {value:+.2f})"


def _live_alpha_resolves(c: Condition, d: Decision, s: Snapshot) -> tuple[str, str]:
    ex = c.params["exchange"]
    live = _live(c, s)
    if live is None or live.alpha_t is None:
        return "unknown", f"no {ex} live alpha"
    state = "fired" if abs(live.alpha_t) >= ALPHA_T_RESOLVES else "armed"
    return state, f"{ex} live alpha t {live.alpha_t:+.2f} (reopens at |t| {ALPHA_T_RESOLVES:.0f})"


def _promotion_after(c: Condition, d: Decision, s: Snapshot) -> tuple[str, str]:
    ex = c.params["exchange"]
    after = [p for p in s.promotions.get(ex, []) if p > d.decided]
    if after:
        return "fired", f"{ex} promoted a candidate on {', '.join(str(p) for p in after)}"
    return "armed", f"no {ex} promotion since {d.decided}"


def _shadow_verdict_saved(c: Condition, d: Decision, s: Snapshot) -> tuple[str, str]:
    if s.verdicts is None:
        return "unknown", "the shadow verdict directory is not visible from here"
    if s.verdicts:
        return "fired", f"shadow verdict saved for {', '.join(sorted(s.verdicts))}"
    return "armed", "no shadow verdict saved yet"


def _option_snapshot_days_at_least(c: Condition, d: Decision, s: Snapshot) -> tuple[str, str]:
    need = int(c.params["days"])
    state = "fired" if s.option_snapshot_days >= need else "armed"
    return state, f"option snapshot days {s.option_snapshot_days} of {need}"


def _manual(c: Condition, d: Decision, s: Snapshot) -> tuple[str, str]:
    return "manual", f"watched by {c.params['watch']}"


#: Each condition type, the parameters it needs, and how it is judged.
CONDITIONS: dict[str, tuple[frozenset[str], Evaluator]] = {
    "live_sessions_at_least": (frozenset({"exchange", "sessions"}), _live_sessions_at_least),
    "live_sharpe_below": (frozenset({"exchange", "value"}), _live_sharpe_below),
    "live_alpha_resolves": (frozenset({"exchange"}), _live_alpha_resolves),
    "promotion_after": (frozenset({"exchange"}), _promotion_after),
    "shadow_verdict_saved": (frozenset(), _shadow_verdict_saved),
    "option_snapshot_days_at_least": (frozenset({"days"}), _option_snapshot_days_at_least),
    "manual": (frozenset({"watch"}), _manual),
}


def parse(entries: list[dict[str, Any]]) -> list[Decision]:
    """Validate the file's entries. A malformed entry fails loudly here, because one that parsed
    into nothing would silently stop watching its decision."""
    decisions: list[Decision] = []
    seen: set[str] = set()
    for entry in entries:
        did = entry.get("id")
        if not did or did in seen:
            raise ValueError(f"decision id missing or repeated: {did!r}")
        seen.add(did)
        if not entry.get("title") or not isinstance(entry.get("decided"), dt.date):
            raise ValueError(f"{did}: needs a title and a `decided` date")
        raw = entry.get("reopen_when") or []
        if not raw:
            raise ValueError(f"{did}: names no condition that would reopen it")
        conditions = []
        for item in raw:
            ctype = item.get("type")
            if ctype not in CONDITIONS:
                raise ValueError(f"{did}: unknown condition type {ctype!r}")
            params = {k: v for k, v in item.items() if k != "type"}
            missing = CONDITIONS[ctype][0] - params.keys()
            if missing:
                raise ValueError(f"{did}: {ctype} is missing {sorted(missing)}")
            # An unexpected key is usually a sentence split by an unquoted comma in YAML's flow
            # style, which would otherwise leave a truncated value standing in for the real one.
            extra = params.keys() - CONDITIONS[ctype][0]
            if extra:
                raise ValueError(
                    f"{did}: {ctype} has unexpected {sorted(extra)} — quote the value?"
                )
            conditions.append(Condition(ctype, params))
        decisions.append(
            Decision(did, entry["title"], entry["decided"], tuple(conditions), entry.get("note"))
        )
    return decisions


def load(path: Path) -> list[Decision]:
    with path.open() as fh:
        return parse(yaml.safe_load(fh) or [])


def evaluate(decisions: list[Decision], snapshot: Snapshot) -> list[Outcome]:
    out = []
    for d in decisions:
        for c in d.conditions:
            state, detail = CONDITIONS[c.type][1](c, d, snapshot)
            out.append(Outcome(d, c, state, detail))
    return out


def collect(engine: Engine, verdict_dir: Path | None) -> Snapshot:
    """Read the figures from the marts, the model runs and the option history."""
    with engine.connect() as conn:
        live_rows = conn.execute(
            text(
                """
                SELECT t.exchange, t.n_days, t.sharpe, t.end_date, a.alpha_t_stat
                FROM analytics.fct_track_record t
                LEFT JOIN analytics.fct_alpha_beta a
                  ON a.exchange = t.exchange AND a.phase = t.phase
                WHERE t.phase = 'live'
                """
            )
        ).all()
        promoted = conn.execute(
            text(
                "SELECT exchange, created_at FROM model_runs "
                "WHERE run_type = 'train' AND decision = 'promoted'"
            )
        ).all()
        days = conn.execute(
            text("SELECT count(DISTINCT snapshot_date) FROM option_quotes")
        ).scalar()
    live = {
        r.exchange: Live(
            int(r.n_days),
            float(r.sharpe) if r.sharpe is not None else None,
            float(r.alpha_t_stat) if r.alpha_t_stat is not None else None,
            r.end_date,
        )
        for r in live_rows
    }
    promotions: dict[str, list[dt.date]] = {}
    for r in promoted:
        local = r.created_at.astimezone(get_exchange(r.exchange).tz).date()
        promotions.setdefault(r.exchange, []).append(local)
    verdicts = None
    if verdict_dir is not None and verdict_dir.is_dir():
        verdicts = frozenset(p.name.split(".")[0] for p in verdict_dir.glob("*.verdict.txt"))
    return Snapshot(live, promotions, int(days or 0), verdicts)
