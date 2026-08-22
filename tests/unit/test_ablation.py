"""Feature ablation, and the interpretation rule that makes its numbers readable.

Thirteen deltas mean nothing on their own: refitting with only the seed changed already
moves IC, so a small delta is indistinguishable from noise. Each market's promotion margin
is two standard deviations of that re-roll, and the verdicts are drawn against it. Getting
that comparison wrong turns noise into a ranked list of "important" features.
"""

import pandas as pd
import pytest

from quantpulse.ml import ablation


@pytest.fixture
def stubbed(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    """Drive the sweep from a table of IC values, so no model is fitted."""

    def _run(full: float, per_feature: dict[str, tuple[float, float]], cols: list[str]):  # type: ignore[no-untyped-def]
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
        return ablation.ablation_report(object(), "XNYS")

    return _run


COLS = ["carries", "useless", "harmful"]


def test_verdicts_are_drawn_against_the_noise_margin(stubbed) -> None:  # type: ignore[no-untyped-def]
    # XNYS margin is 0.006. Removing `carries` costs more than that; removing `useless`
    # costs less than it; removing `harmful` improves IC by more than it.
    table = stubbed(
        0.100,
        {"carries": (0.080, 0.05), "useless": (0.098, 0.01), "harmful": (0.110, 0.00)},
        COLS,
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
    )
    verdicts = dict(zip(table["feature"], table["verdict"], strict=True))
    assert verdicts["carries"] == "within noise — not shown to contribute"  # 0.0059 < 0.006


def test_rows_are_ordered_by_how_much_removal_hurts(stubbed) -> None:  # type: ignore[no-untyped-def]
    """Most load-bearing first, so the useless tail is visible at the bottom."""
    table = stubbed(
        0.100,
        {"carries": (0.080, 0.05), "useless": (0.098, 0.01), "harmful": (0.110, 0.00)},
        COLS,
    )
    assert list(table["feature"]) == ["carries", "useless", "harmful"]


def test_the_report_carries_the_margin_it_judged_against(stubbed) -> None:  # type: ignore[no-untyped-def]
    """A reader cannot check a verdict without the threshold that produced it."""
    table = stubbed(0.1, dict.fromkeys(COLS, (0.1, 0.0)), COLS)
    assert table.attrs["noise_margin"] == pytest.approx(0.006)
    assert table.attrs["full_ic"] == pytest.approx(0.1)


def test_a_subset_that_cannot_be_fitted_is_reported_not_ranked(stubbed) -> None:  # type: ignore[no-untyped-def]
    """NaN must not sort as if it were a delta — a failed fit is missing evidence, not a
    feature that contributes nothing."""
    table = stubbed(
        0.100,
        {"carries": (0.080, 0.05), "useless": (float("nan"), 0.01), "harmful": (0.110, 0.0)},
        COLS,
    )
    verdicts = dict(zip(table["feature"], table["verdict"], strict=True))
    assert verdicts["useless"] == "could not fit"
