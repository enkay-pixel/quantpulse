"""Feature ablation, and the interpretation rule that makes its numbers readable.

A single IC means nothing on its own: refitting with only the seed changed already moves it,
on this panel by more than any one feature is worth. So every comparison here is *paired* on
the seed — a subset is scored against the full model fitted with the same seed — and the
verdict comes from the spread of those paired differences rather than from comparing one
point estimate to one global threshold.

That distinction is the whole test surface. An unpaired sweep judged against a global floor
reports a feature as harmful when one seed happened to favour it, which is a false positive
that looks exactly like a finding.
"""

import pandas as pd
import pytest

from quantpulse.ml import ablation


@pytest.fixture
def report(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    """Drive the sweep from per-seed IC tables, so no model is fitted."""

    def _run(full: dict[int, float], drops: dict[str, dict[int, float]], cols: list[str]):  # type: ignore[no-untyped-def]
        seeds = tuple(full)
        monkeypatch.setattr(ablation, "FEATURE_COLUMNS", tuple(cols))
        monkeypatch.setattr(
            "quantpulse.ml.pipeline.build_dataset", lambda *a, **k: pd.DataFrame({"x": [1]})
        )

        def fake_score(frame, subset, params, cfg):  # type: ignore[no-untyped-def]
            if len(subset) == len(cols):
                return full[cfg.seed]
            if len(subset) == 1:
                return 0.0
            (missing,) = [c for c in cols if c not in subset]
            return drops[missing][cfg.seed]

        monkeypatch.setattr(ablation, "_score_subset", fake_score)
        return ablation.ablation_report(object(), "XNYS", seeds=seeds)

    return _run


COLS = ["steady", "flaky", "helpful"]
SEEDS = (1, 2, 3, 4, 5)
FULL = dict.fromkeys(SEEDS, 0.010)


def test_a_consistent_delta_is_called_a_finding(report) -> None:  # type: ignore[no-untyped-def]
    """Dropping `steady` raises IC by the same amount whatever the seed, so the effect is the
    feature and not the draw."""
    table = report(
        FULL,
        {
            "steady": dict(zip(SEEDS, [0.030, 0.031, 0.029, 0.030, 0.030], strict=True)),
            "flaky": dict(zip(SEEDS, [0.010] * 5, strict=True)),
            "helpful": dict(zip(SEEDS, [0.010] * 5, strict=True)),
        },
        COLS,
    )
    verdicts = dict(zip(table["feature"], table["verdict"], strict=True))
    assert verdicts["steady"] == "costs signal — removing it helps"


def test_a_sign_flipping_delta_is_not_a_finding(report) -> None:  # type: ignore[no-untyped-def]
    """The regression this guards: `flaky` has a *positive mean* delta of the same order as
    `steady`, but its per-seed differences change sign. One unpaired draw would report it as
    harmful; paired across seeds it is nothing. This is exactly how a real feature was
    misreported — the sweep had quoted its single most favourable seed."""
    table = report(
        FULL,
        {
            "steady": dict(zip(SEEDS, [0.030, 0.031, 0.029, 0.030, 0.030], strict=True)),
            "flaky": dict(zip(SEEDS, [0.044, 0.032, 0.012, 0.001, 0.011], strict=True)),
            "helpful": dict(zip(SEEDS, [0.010] * 5, strict=True)),
        },
        COLS,
    )
    rows = {r["feature"]: r for r in table.to_dict("records")}
    # Both look similar on the mean; only the error separates them.
    assert rows["flaky"]["delta"] > 0
    assert rows["flaky"]["delta_se"] > rows["steady"]["delta_se"] * 3
    assert rows["flaky"]["verdict"] == "within noise — not shown to contribute"


def test_a_feature_that_carries_signal_is_named(report) -> None:  # type: ignore[no-untyped-def]
    """Dropping it consistently *lowers* IC, which is the one case worth keeping a feature for."""
    table = report(
        FULL,
        {
            "steady": dict(zip(SEEDS, [0.010] * 5, strict=True)),
            "flaky": dict(zip(SEEDS, [0.010] * 5, strict=True)),
            "helpful": dict(zip(SEEDS, [-0.010, -0.011, -0.009, -0.010, -0.010], strict=True)),
        },
        COLS,
    )
    verdicts = dict(zip(table["feature"], table["verdict"], strict=True))
    assert verdicts["helpful"] == "carries signal"


def test_the_comparison_is_paired_on_the_seed(report) -> None:  # type: ignore[no-untyped-def]
    """Full-model IC swings hugely with the seed while every subset tracks it exactly. Paired,
    the deltas are identically zero and nothing is reported. Comparing means instead would
    carry that swing into every feature's verdict."""
    swinging = dict(zip(SEEDS, [0.05, -0.03, 0.11, -0.06, 0.02], strict=True))
    table = report(
        swinging,
        {c: dict(swinging) for c in COLS},
        COLS,
    )
    assert set(table["verdict"]) == {"within noise — not shown to contribute"}
    assert table["delta"].abs().max() == pytest.approx(0.0)
    # The spread is what proves the pairing happened. Comparing against the mean full-model
    # IC instead would leave every seed's swing in the differences, and the mean delta would
    # still be zero — so only the standard error distinguishes the two.
    assert table["delta_se"].max() == pytest.approx(0.0)


def test_a_subset_that_cannot_be_fitted_is_reported_not_ranked(report) -> None:  # type: ignore[no-untyped-def]
    """NaN must not sort as if it were a delta — a failed fit is missing evidence, not a
    feature that contributes nothing."""
    table = report(
        FULL,
        {
            "steady": dict(zip(SEEDS, [0.030] * 5, strict=True)),
            "flaky": dict.fromkeys(SEEDS, float("nan")),
            "helpful": dict(zip(SEEDS, [0.010] * 5, strict=True)),
        },
        COLS,
    )
    verdicts = dict(zip(table["feature"], table["verdict"], strict=True))
    assert verdicts["flaky"] == "could not measure"


def test_a_partly_unfittable_subset_is_judged_on_the_seeds_that_worked(report) -> None:  # type: ignore[no-untyped-def]
    """One bad fit must not erase the evidence from the others. A NaN left in the differences
    poisons the mean and the whole feature reads as unmeasurable, discarding seeds that
    scored perfectly well."""
    table = report(
        FULL,
        {
            "steady": dict(zip(SEEDS, [0.030] * 5, strict=True)),
            "flaky": dict(
                zip(SEEDS, [0.030, float("nan"), 0.031, 0.029, float("nan")], strict=True)
            ),
            "helpful": dict(zip(SEEDS, [0.010] * 5, strict=True)),
        },
        COLS,
    )
    rows = {r["feature"]: r for r in table.to_dict("records")}
    assert rows["flaky"]["verdict"] == "costs signal — removing it helps"
    assert rows["flaky"]["delta"] == pytest.approx(0.020, abs=1e-3)


def test_the_report_says_how_many_seeds_backed_it(report) -> None:  # type: ignore[no-untyped-def]
    """A t-statistic is unreadable without knowing how many paired differences produced it."""
    table = report(FULL, {c: dict(FULL) for c in COLS}, COLS)
    assert table.attrs["seeds"] == len(SEEDS)
    assert table.attrs["full_ic"] == pytest.approx(0.010)


# --- the measured floor ------------------------------------------------------------------


def test_the_floor_is_two_sd_of_the_seed_reroll(monkeypatch: pytest.MonkeyPatch) -> None:
    """Borrowing a floor measured under a different procedure is what turns seed noise into
    a ranked list, so this number has to come from re-rolling the seed here."""
    import numpy as np

    values = [0.01, 0.02, 0.03, 0.04, 0.05, 0.02, 0.03, 0.01, 0.04, 0.05]
    seen = iter(values)
    monkeypatch.setattr(ablation, "_score_subset", lambda *a, **k: next(seen))
    floor = ablation.measured_noise_floor(pd.DataFrame({"x": [1]}), ["a"], ablation.TrainConfig())
    assert floor == pytest.approx(2 * np.std(values, ddof=1))


def test_every_seed_is_actually_varied(monkeypatch: pytest.MonkeyPatch) -> None:
    """A floor measured with one seed reused is identically zero, which would pass every
    feature as significant rather than none."""
    seeds = []
    monkeypatch.setattr(
        ablation, "_score_subset", lambda f, c, p, cfg: (seeds.append(cfg.seed), 0.0)[1]
    )
    ablation.measured_noise_floor(pd.DataFrame({"x": [1]}), ["a"], ablation.TrainConfig())
    assert sorted(seeds) == sorted(ablation.NOISE_SEEDS)


def test_a_floor_needs_at_least_two_fits(monkeypatch: pytest.MonkeyPatch) -> None:
    """One surviving fit has no spread, and reporting 0.0 would call every delta significant."""
    monkeypatch.setattr(ablation, "_score_subset", lambda *a, **k: float("nan"))
    floor = ablation.measured_noise_floor(pd.DataFrame({"x": [1]}), ["a"], ablation.TrainConfig())
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

        def fake_score(f, subset, params, cfg):  # type: ignore[no-untyped-def]
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
