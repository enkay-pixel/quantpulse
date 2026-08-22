"""Feature ablation, and the interpretation rule that makes its numbers readable.

Thirteen deltas mean nothing on their own: refitting with only the seed changed already
moves IC, so a small delta is indistinguishable from noise. The verdicts are drawn against
a floor *measured under the same procedure*, and getting that comparison wrong turns noise
into a ranked list of "important" features — a borrowed floor several times too small
ranks every feature and reads as a finding.

The floor is stubbed to a known value in most tests so the verdict logic is what is under
test; the measurement itself is covered separately.
"""

import pandas as pd
import pytest

from quantpulse.ml import ablation


@pytest.fixture
def stubbed(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    """Drive the sweep from a table of IC values, so no model is fitted."""

    def _run(
        full: float,
        per_feature: dict[str, tuple[float, float]],
        cols: list[str],
        margin: float = 0.023,
    ):  # type: ignore[no-untyped-def]
        monkeypatch.setattr(ablation, "FEATURE_COLUMNS", tuple(cols))
        monkeypatch.setattr(
            "quantpulse.ml.pipeline.build_dataset", lambda *a, **k: pd.DataFrame({"x": [1]})
        )

        def fake_score(frame, subset, params, cfg, width, holdout_fraction):  # type: ignore[no-untyped-def]
            if len(subset) == len(cols):
                return full
            if len(subset) == 1:
                return per_feature[subset[0]][1]
            (missing,) = [c for c in cols if c not in subset]
            return per_feature[missing][0]

        monkeypatch.setattr(ablation, "_score_subset", fake_score)
        monkeypatch.setattr(ablation, "measured_noise_floor", lambda *a, **k: margin)
        return ablation.ablation_report(object(), "XNYS")

    return _run


COLS = ["carries", "useless", "harmful"]


def test_verdicts_are_drawn_against_the_noise_margin(stubbed) -> None:  # type: ignore[no-untyped-def]
    # The floor is stubbed to 0.006. Removing `carries` costs more than that; removing `useless`
    # costs less than it; removing `harmful` improves IC by more than it.
    table = stubbed(
        0.100,
        {"carries": (0.080, 0.05), "useless": (0.098, 0.01), "harmful": (0.110, 0.00)},
        COLS,
        margin=0.006,
    )
    verdicts = dict(zip(table["feature"], table["verdict"], strict=True))
    assert verdicts["carries"] == "carries signal"
    assert verdicts["useless"] == "within noise — not shown to contribute"
    assert verdicts["harmful"] == "costs signal — removing it helps"


def test_a_delta_just_inside_the_margin_is_not_called_signal(stubbed) -> None:  # type: ignore[no-untyped-def]
    """The boundary is the whole point. A feature whose removal costs slightly less than the
    seed re-roll has not been shown to do anything, and calling it important would dress
    noise as a finding."""
    table = stubbed(
        0.100,
        {"carries": (0.0941, 0.05), "useless": (0.0995, 0.01), "harmful": (0.100, 0.0)},
        COLS,
        margin=0.006,
    )
    verdicts = dict(zip(table["feature"], table["verdict"], strict=True))
    assert verdicts["carries"] == "within noise — not shown to contribute"  # 0.0059 < 0.006


def test_rows_are_ordered_by_how_much_removal_hurts(stubbed) -> None:  # type: ignore[no-untyped-def]
    """Most load-bearing first, so the useless tail is visible at the bottom."""
    table = stubbed(
        0.100,
        {"carries": (0.080, 0.05), "useless": (0.098, 0.01), "harmful": (0.110, 0.00)},
        COLS,
        margin=0.006,
    )
    assert list(table["feature"]) == ["carries", "useless", "harmful"]


def test_the_report_carries_the_margin_it_judged_against(stubbed) -> None:  # type: ignore[no-untyped-def]
    """A reader cannot check a verdict without the threshold that produced it — and the
    threshold is measured per run, so it cannot be looked up anywhere else."""
    table = stubbed(0.1, dict.fromkeys(COLS, (0.1, 0.0)), COLS)
    # Deliberately not 0.006 — that is XNYS's promotion margin, and a floor that silently
    # fell back to it would pass this assertion by coincidence.
    assert table.attrs["noise_margin"] == pytest.approx(0.023)
    assert table.attrs["full_ic"] == pytest.approx(0.1)


def test_a_subset_that_cannot_be_fitted_is_reported_not_ranked(stubbed) -> None:  # type: ignore[no-untyped-def]
    """NaN must not sort as if it were a delta — a failed fit is missing evidence, not a
    feature that contributes nothing."""
    table = stubbed(
        0.100,
        {"carries": (0.080, 0.05), "useless": (float("nan"), 0.01), "harmful": (0.110, 0.0)},
        COLS,
        margin=0.006,
    )
    verdicts = dict(zip(table["feature"], table["verdict"], strict=True))
    assert verdicts["useless"] == "could not fit"


# --- the measured floor ------------------------------------------------------------------


def test_the_floor_is_two_sd_of_the_seed_reroll(monkeypatch: pytest.MonkeyPatch) -> None:
    """Borrowing a floor measured under a different procedure is what turns seed noise into
    a ranked list, so this number has to come from re-rolling the seed here."""
    import numpy as np

    seen = iter([0.01, 0.02, 0.03, 0.04, 0.05])
    monkeypatch.setattr(ablation, "_score_subset", lambda *a, **k: next(seen))
    floor = ablation.measured_noise_floor(
        pd.DataFrame({"x": [1]}), ["a"], ablation.TrainConfig(), 0.2, 0.15
    )
    assert floor == pytest.approx(2 * np.std([0.01, 0.02, 0.03, 0.04, 0.05], ddof=1))


def test_every_seed_is_actually_varied(monkeypatch: pytest.MonkeyPatch) -> None:
    """A floor measured with one seed reused is identically zero, which would pass every
    feature as significant rather than none."""
    seeds = []
    monkeypatch.setattr(
        ablation, "_score_subset", lambda f, c, p, cfg, w, h: (seeds.append(cfg.seed), 0.0)[1]
    )
    ablation.measured_noise_floor(
        pd.DataFrame({"x": [1]}), ["a"], ablation.TrainConfig(), 0.2, 0.15
    )
    assert sorted(seeds) == sorted(ablation.NOISE_SEEDS)


def test_a_floor_needs_at_least_two_fits(monkeypatch: pytest.MonkeyPatch) -> None:
    """One surviving fit has no spread, and reporting 0.0 would call every delta significant."""
    monkeypatch.setattr(ablation, "_score_subset", lambda *a, **k: float("nan"))
    floor = ablation.measured_noise_floor(
        pd.DataFrame({"x": [1]}), ["a"], ablation.TrainConfig(), 0.2, 0.15
    )
    assert floor != floor  # NaN


# --- forward selection -------------------------------------------------------------------


@pytest.fixture
def selector(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    """Drive selection from a table keyed by the chosen subset, fitting nothing."""

    def _run(inner: dict[tuple[str, ...], float], cols: list[str], floor: float = 0.01):  # type: ignore[no-untyped-def]
        frame = pd.DataFrame({"x": range(100)})
        train = frame.iloc[:80]
        monkeypatch.setattr(ablation, "FEATURE_COLUMNS", tuple(cols))
        monkeypatch.setattr("quantpulse.ml.pipeline.build_dataset", lambda *a, **k: frame)
        monkeypatch.setattr(
            "quantpulse.ml.training.split_by_date", lambda *a, **k: (train, frame.iloc[80:])
        )
        monkeypatch.setattr(ablation, "measured_noise_floor", lambda *a, **k: floor)
        monkeypatch.setattr(ablation, "train_final_model", lambda *a, **k: (None, frame))
        monkeypatch.setattr(
            "quantpulse.ml.baselines.standing_competitor_metrics",
            lambda *a, **k: {"holdout_ic": 0.0},
        )
        scored_on = []

        def fake_score(f, subset, params, cfg, width, holdout_fraction):  # type: ignore[no-untyped-def]
            scored_on.append((len(f), tuple(subset)))
            return inner.get(tuple(subset), 0.0)

        monkeypatch.setattr(ablation, "_score_subset", fake_score)
        return ablation.forward_select(object(), "XNYS"), scored_on

    return _run


def test_selection_never_scores_against_the_holdout(selector) -> None:  # type: ignore[no-untyped-def]
    """Choosing features by holdout IC fits the choice to the holdout, and the final number
    would then describe that fit rather than out-of-sample behaviour."""
    sel, scored_on = selector({("a",): 0.5, ("a", "b"): 0.9}, ["a", "b", "c"])
    # Everything scored before the final evaluation must have seen the 80-row train split.
    during_selection = [rows for rows, subset in scored_on if len(subset) < 3][:-1]
    assert during_selection and all(rows == 80 for rows in during_selection)
    assert sel.chosen == ["a", "b"]


def test_a_market_where_nothing_works_selects_nothing(selector) -> None:  # type: ignore[no-untyped-def]
    """The empty set has no skill, so the first feature must clear the floor above zero.
    Seeding the running best at -inf admits it whatever it scored, and a market with no
    signal would still report one 'selected' feature."""
    sel, _ = selector({("a",): 0.005, ("b",): 0.004, ("c",): 0.001}, ["a", "b", "c"], floor=0.01)
    assert sel.chosen == []
    assert sel.pruned_ic != sel.pruned_ic  # NaN — nothing to measure


def test_adding_stops_when_the_gain_is_inside_the_floor(selector) -> None:  # type: ignore[no-untyped-def]
    """A feature is admitted on evidence, not on a positive-looking rounding error."""
    sel, _ = selector(
        {("a",): 0.5, ("a", "b"): 0.505, ("a", "c"): 0.502}, ["a", "b", "c"], floor=0.01
    )
    assert sel.chosen == ["a"]  # +0.005 and +0.002 are both inside the floor


def test_the_selection_carries_both_floors(selector) -> None:  # type: ignore[no-untyped-def]
    """The inner split is smaller and noisier than the holdout, so the two thresholds differ
    and a reader checking either number needs the one it was judged against."""
    sel, _ = selector({("a",): 0.5}, ["a", "b", "c"])
    assert sel.noise_margin == pytest.approx(0.01)
    assert sel.inner_margin == pytest.approx(0.01)
