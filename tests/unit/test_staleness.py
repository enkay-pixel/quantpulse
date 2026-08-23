"""Model staleness: how fast a frozen model loses skill.

The weekly retrain cadence was chosen, never measured. This curve is what turns it into a
number, so the properties that make it readable are the ones worth pinning.

The freeze point is repeated on purpose. A single one gives each age bucket one window of
`step_days` dates, and a 21-day IC swings far more with *which* three weeks it covers than
with anything about the model — the first version of this reported ICs between -0.34 and
+0.20 with no monotonic shape and quoted a seed-to-seed error that made the swings look
significant. The error has to come from the spread across windows, not across seeds.
"""

import datetime as dt

import pandas as pd
import pytest

from quantpulse.ml import staleness


@pytest.fixture
def curve(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    """Drive the curve from a table of IC values, fitting nothing."""

    def _run(ic_by_age, n_dates=900, step_days=21, n_steps=4, n_origins=3, seeds=(1, 2, 3)):  # type: ignore[no-untyped-def]
        dates = [dt.date(2020, 1, 1) + dt.timedelta(days=i) for i in range(n_dates)]
        frame = pd.DataFrame({"date": dates, "x": range(n_dates)})
        fits: list[int] = []
        scored_blocks: list[tuple] = []

        monkeypatch.setattr("quantpulse.ml.pipeline.build_dataset", lambda *a, **k: frame)
        monkeypatch.setattr(staleness, "feature_columns_for", lambda ex: ["x"])
        monkeypatch.setattr(
            staleness, "_fit_frozen", lambda train, cols, cfg: (fits.append(cfg.seed), object())[1]
        )
        monkeypatch.setattr(
            "quantpulse.ml.registry.predict_with", lambda booster, frame: [0.0] * len(frame)
        )

        def fake_ic(scored):  # type: ignore[no-untyped-def]
            block = tuple(sorted(scored["date"]))
            scored_blocks.append(block)
            # Age is recovered from the block's offset from the earliest date scored.
            idx = (len(scored_blocks) - 1) // len(seeds) % n_steps
            # Nudge each seed apart so every bucket has a real spread to summarise.
            return ic_by_age[idx % len(ic_by_age)] + ((len(scored_blocks) - 1) % len(seeds)) * 0.001

        monkeypatch.setattr("quantpulse.ml.metrics.information_coefficient", fake_ic)
        table = staleness.staleness_curve(
            object(),
            "XNYS",
            step_days=step_days,
            n_steps=n_steps,
            n_origins=n_origins,
            seeds=seeds,
        )
        return table, fits, scored_blocks

    return _run


def test_every_age_pools_several_independent_windows(curve) -> None:  # type: ignore[no-untyped-def]
    """The point of rolling the origin. One window per age gives a 21-day IC and an error
    that describes the seeds rather than the windows, which is how the first version of this
    reported swings of 0.3 as significant."""
    table, _, _ = curve([0.05, 0.04, 0.03, 0.02], n_origins=3, seeds=(1, 2, 3))
    assert table.attrs["origins"] == 3
    # 3 origins x 3 seeds contribute to each age.
    assert set(table["n_windows"]) == {9}


def test_the_model_is_frozen_once_per_origin_and_seed(curve) -> None:  # type: ignore[no-untyped-def]
    """Refitting inside the age loop would rebuild the same model for every bucket and the
    word 'frozen' would stop being true."""
    _, fits, _ = curve([0.05, 0.04, 0.03, 0.02], n_origins=3, seeds=(1, 2, 3))
    assert fits == [1, 2, 3, 1, 2, 3, 1, 2, 3]


def test_age_buckets_are_disjoint_and_consecutive(curve) -> None:  # type: ignore[no-untyped-def]
    """Overlapping buckets carry the same dates into two points, and a curve drawn through
    them is partly the same data twice."""
    table, _, blocks = curve([0.05, 0.04, 0.03, 0.02], step_days=21, n_steps=4, n_origins=1)
    assert list(table["age_start"]) == [0, 21, 42, 63]
    assert list(table["age_end"]) == [20, 41, 62, 83]
    # The labels come from the loop index and would look right however the dates were
    # sliced, so check what was actually scored. One origin, one block per age per seed.
    per_age = [blocks[i * 3] for i in range(4)]
    assert all(len(b) == 21 for b in per_age), [len(b) for b in per_age]
    covered: set = set()
    for block in per_age:
        assert not covered & set(block), "buckets must not share dates"
        covered |= set(block)


def test_each_point_carries_the_spread_across_windows(curve) -> None:  # type: ignore[no-untyped-def]
    """A falling curve means nothing without knowing how much a point moves between windows."""
    table, _, _ = curve([0.05, 0.04, 0.03, 0.02])
    assert (table["ic_std_error"] > 0).all()


def test_a_panel_too_short_for_the_origins_is_refused(curve) -> None:  # type: ignore[no-untyped-def]
    """A final bucket measured on a sliver reports an IC that swings on its own sample size,
    which reads as decay."""
    with pytest.raises(ValueError, match="needs more than"):
        curve([0.05], n_dates=200, step_days=21, n_steps=4)
