"""Guards on the fixed-defaults comparison.

What makes this comparison honest is that the fixed configurations are defined by rule and never
by result, that the one eligible for adoption is named in advance, and that the decision rule asks
about the worst plausible loss rather than the average one. Each of those is pinned here, because
each could be loosened without any test noticing and would then produce a more favourable answer.
"""

import math

import pytest

from quantpulse.data.calendar import get_exchange
from quantpulse.ml import fixed_defaults as fd
from quantpulse.ml import training
from quantpulse.ml.fixed_defaults import (
    ARMS,
    CANDIDATE,
    CONTROL,
    fixed_default,
    non_inferiority,
    search_center,
)
from quantpulse.ml.training import DEFAULT_PARAMS, LEARNING_RATE_FLOOR, SEARCH_BOUNDS

MARKETS = ("XJSE", "XNYS")


@pytest.mark.parametrize("market", MARKETS)
def test_no_fixed_configuration_exceeds_the_markets_ceiling(market: str) -> None:
    """The defaults' rate sits above the JSE ceiling, which exists because rates above it were
    measured to collapse candidates there. A fixed arm that ignored it would be testing a
    configuration the pipeline has already ruled out."""
    ceiling = get_exchange(market).learning_rate_ceiling
    for config in (fixed_default(ceiling), search_center(ceiling)):
        assert LEARNING_RATE_FLOOR <= config["learning_rate"] <= ceiling


def test_fixed_default_is_the_pipelines_defaults_with_only_the_rate_clipped() -> None:
    ceiling = get_exchange("XJSE").learning_rate_ceiling
    config = fixed_default(ceiling)
    assert config["learning_rate"] == min(DEFAULT_PARAMS["learning_rate"], ceiling)
    for key, value in DEFAULT_PARAMS.items():
        if key != "learning_rate":
            assert config[key] == value, f"{key} changed — the arm is no longer 'the defaults'"
    # Uncapped, the defaults pass through untouched.
    assert fixed_default(1.0)["learning_rate"] == DEFAULT_PARAMS["learning_rate"]


@pytest.mark.parametrize("market", MARKETS)
def test_search_center_is_the_midpoint_on_the_scale_the_search_uses(market: str) -> None:
    ceiling = get_exchange(market).learning_rate_ceiling
    center = search_center(ceiling)
    # The rate is searched log-uniformly, so its centre is geometric.
    assert center["learning_rate"] == pytest.approx(math.sqrt(LEARNING_RATE_FLOOR * ceiling))
    for name, (low, high, log) in SEARCH_BOUNDS.items():
        expected = math.sqrt(low * high) if log else (low + high) / 2
        assert low <= center[name] <= high
        assert center[name] == pytest.approx(expected, abs=0.5), name
    for name in training.INTEGER_PARAMS:
        assert isinstance(center[name], int), f"{name} must be an integer, as the search draws it"


def test_search_center_reads_the_bounds_the_search_reads(monkeypatch: pytest.MonkeyPatch) -> None:
    """The centre is only the centre of the real space if it cannot drift from it.

    Widening a bound must move the centre. If it did not, the centre would be a copy of the space
    as it once was, and the arm would be testing a point nobody searches around any more.
    """
    before = search_center(0.2)["num_leaves"]
    widened = {**SEARCH_BOUNDS, "num_leaves": (8, 200, False)}
    monkeypatch.setattr(fd, "SEARCH_BOUNDS", widened)
    assert search_center(0.2)["num_leaves"] != before
    assert search_center(0.2)["num_leaves"] == round((8 + 200) / 2)


def test_the_adoption_candidate_is_named_in_advance() -> None:
    """Choosing between the fixed arms by which scored better would be selecting on the holdout by
    a shorter route, so exactly one is eligible and it is fixed before the run."""
    assert CANDIDATE == "fixed_default"
    assert CANDIDATE in ARMS
    assert CONTROL in ARMS
    assert CANDIDATE != CONTROL


def test_truncate_panel_cuts_on_the_panels_own_date_type() -> None:
    """The panel holds `datetime.date`. A cutoff parsed to a pandas Timestamp cannot be compared
    with it, and the first version did exactly that — it crashed on first use, and the crash was
    easy to miss because a stale output file from an earlier run was still sitting there."""
    import datetime as dt

    import pandas as pd

    from quantpulse.ml.fixed_defaults import truncate_panel

    frame = pd.DataFrame(
        {"date": [dt.date(2026, 8, d) for d in (24, 25, 26, 27)], "x": [1, 2, 3, 4]}
    )
    kept = truncate_panel(frame, "2026-08-26")
    assert list(kept["date"]) == [dt.date(2026, 8, d) for d in (24, 25, 26)]
    # Inclusive of the cutoff itself, so "as of" a date includes that date.
    assert dt.date(2026, 8, 26) in set(kept["date"])
    # No cutoff means the whole panel — not an empty one.
    assert truncate_panel(frame, None) is frame


def test_non_inferiority_asks_about_the_worst_plausible_loss() -> None:
    margin = 0.008
    # Well inside: a small loss, tightly measured.
    lower, ok = non_inferiority(-0.001, 0.001, margin)
    assert ok and lower == pytest.approx(-0.001 - 1.645 * 0.001)
    # A point estimate of zero is not enough when the error is wide — this is unresolved, and a
    # rule that passed it would be accepting the arm on no evidence.
    _, ok = non_inferiority(0.0, 0.010, margin)
    assert not ok
    # A better arm passes, however noisy, once its bound clears the margin.
    _, ok = non_inferiority(+0.020, 0.005, margin)
    assert ok
    # Exactly at the margin does not pass: the bound must be strictly better than -margin. Built
    # with no error term so the boundary is exact — a case that relied on the interval arithmetic
    # cancelling would pass or fail on floating-point rounding rather than on the rule.
    _, ok = non_inferiority(-margin, 0.0, margin)
    assert not ok
    _, ok = non_inferiority(-margin + 1e-9, 0.0, margin)
    assert ok
