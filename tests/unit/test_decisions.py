"""Standing decisions: the file parses whole, and each condition fires on its own threshold.

A decision whose conditions are mis-parsed is worse than one with none: it looks watched and is
not. So the file is validated strictly, and two YAML traps that produced exactly that while it was
written are pinned — a ` #` starting a comment mid-title, and an unquoted comma splitting a value
into a stray key.
"""

import datetime as dt
import re
from collections.abc import Mapping
from pathlib import Path

import pytest

from quantpulse.monitoring.decisions import (
    Condition,
    Decision,
    Live,
    Snapshot,
    evaluate,
    load,
    parse,
)

DECISIONS_FILE = Path(__file__).resolve().parents[2] / "configs" / "decisions.yaml"
DECIDED = dt.date(2026, 10, 1)


def test_the_real_file_parses_and_every_title_survives_whole() -> None:
    decisions = load(DECISIONS_FILE)
    assert decisions, "the file holds no decisions"
    raw = [
        m.group(1).strip().strip('"').strip("'")
        for m in re.finditer(r"^  title: (.*)$", DECISIONS_FILE.read_text(), re.M)
    ]
    assert [d.title for d in decisions] == raw, "a title was cut short — an unquoted ' #'?"


def _entry(**condition: object) -> dict[str, object]:
    return {"id": "d", "title": "t", "decided": DECIDED, "reopen_when": [condition]}


@pytest.mark.parametrize(
    ("entry", "complaint"),
    [
        (_entry(type="no_such_type"), "unknown condition type"),
        (_entry(type="live_sessions_at_least", exchange="XJSE"), "missing"),
        (_entry(type="manual", watch="a check", **{"which reports a fix": None}), "unexpected"),
        ({"id": "d", "title": "t", "decided": DECIDED, "reopen_when": []}, "names no condition"),
        ({"id": "d", "title": "t", "reopen_when": [{"type": "manual", "watch": "x"}]}, "decided"),
    ],
)
def test_a_malformed_entry_fails_loudly(entry: dict[str, object], complaint: str) -> None:
    with pytest.raises(ValueError, match=complaint):
        parse([entry])


def test_a_repeated_id_fails_loudly() -> None:
    entry = _entry(type="manual", watch="x")
    with pytest.raises(ValueError, match="repeated"):
        parse([entry, dict(entry)])


def _snapshot(**overrides: object) -> Snapshot:
    base: dict[str, object] = {
        "live": {
            "XJSE": Live(sessions=60, sharpe=0.5, alpha_t=1.0, end_date=dt.date(2026, 10, 16))
        },
        "promotions": {"XJSE": [dt.date(2026, 7, 25)]},
        "option_snapshot_days": 100,
        "verdicts": frozenset(),
    }
    base.update(overrides)
    return Snapshot(**base)  # type: ignore[arg-type]


def _state(condition: Mapping[str, object], snapshot: Snapshot) -> str:
    (outcome,) = evaluate(parse([_entry(**condition)]), snapshot)
    return outcome.state


def test_a_session_count_fires_on_reaching_it_not_after() -> None:
    cond = {"type": "live_sessions_at_least", "exchange": "XJSE", "sessions": 60}
    assert _state(cond, _snapshot()) == "fired"
    below = {"XJSE": Live(59, 0.5, 1.0, None)}
    assert _state(cond, _snapshot(live=below)) == "armed"


def test_a_sharpe_threshold_is_strict() -> None:
    cond = {"type": "live_sharpe_below", "exchange": "XJSE", "value": 0}
    assert _state(cond, _snapshot(live={"XJSE": Live(60, 0.0, 1.0, None)})) == "armed"
    assert _state(cond, _snapshot(live={"XJSE": Live(60, -0.01, 1.0, None)})) == "fired"


@pytest.mark.parametrize(("t", "state"), [(2.0, "fired"), (-2.1, "fired"), (1.99, "armed")])
def test_alpha_resolving_either_way_fires(t: float, state: str) -> None:
    cond = {"type": "live_alpha_resolves", "exchange": "XJSE"}
    assert _state(cond, _snapshot(live={"XJSE": Live(60, 0.5, t, None)})) == state


def test_only_a_promotion_after_the_decision_fires() -> None:
    cond = {"type": "promotion_after", "exchange": "XJSE"}
    assert _state(cond, _snapshot()) == "armed", "a promotion before the decision reopened it"
    same_day = {"XJSE": [DECIDED]}
    assert _state(cond, _snapshot(promotions=same_day)) == "armed", "the decision's own day counted"
    later = {"XJSE": [dt.date(2026, 7, 25), DECIDED + dt.timedelta(days=1)]}
    assert _state(cond, _snapshot(promotions=later)) == "fired"


def test_an_unseen_verdict_directory_is_unknown_not_none_saved() -> None:
    cond = {"type": "shadow_verdict_saved"}
    assert _state(cond, _snapshot(verdicts=None)) == "unknown"
    assert _state(cond, _snapshot(verdicts=frozenset())) == "armed"
    assert _state(cond, _snapshot(verdicts=frozenset({"XJSE"}))) == "fired"


def test_a_missing_live_record_is_unknown() -> None:
    cond = {"type": "live_sessions_at_least", "exchange": "XNYS", "sessions": 60}
    assert _state(cond, _snapshot()) == "unknown"


def test_option_days_and_manual_conditions() -> None:
    days = {"type": "option_snapshot_days_at_least", "days": 100}
    assert _state(days, _snapshot()) == "fired"
    assert _state(days, _snapshot(option_snapshot_days=99)) == "armed"
    assert _state({"type": "manual", "watch": "a person"}, _snapshot()) == "manual"


def test_every_condition_of_a_decision_is_reported() -> None:
    d = Decision(
        "d",
        "t",
        DECIDED,
        (
            Condition("live_sessions_at_least", {"exchange": "XJSE", "sessions": 60}),
            Condition("live_sharpe_below", {"exchange": "XJSE", "value": 0}),
        ),
    )
    assert [o.state for o in evaluate([d], _snapshot())] == ["fired", "armed"]
