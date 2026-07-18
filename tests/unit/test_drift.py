import datetime as dt

import numpy as np
import pandas as pd

from quantpulse.features.engineering import FEATURE_COLUMNS
from quantpulse.monitoring.drift import (
    compute_drift,
    population_stability_index,
)


def frame_from(rng: np.random.Generator, loc: float, n: int = 500) -> pd.DataFrame:
    data = {c: rng.normal(loc, 1.0, n) for c in FEATURE_COLUMNS}
    return pd.DataFrame(data)


def test_psi_identical_distributions_near_zero() -> None:
    rng = np.random.default_rng(0)
    ref = rng.normal(0, 1, 5000)
    cur = rng.normal(0, 1, 5000)
    assert population_stability_index(ref, cur) < 0.05


def test_psi_shifted_distribution_is_large() -> None:
    rng = np.random.default_rng(0)
    ref = rng.normal(0, 1, 5000)
    cur = rng.normal(2, 1, 5000)
    assert population_stability_index(ref, cur) > 0.5


def test_psi_constant_reference_degenerates_to_zero() -> None:
    assert population_stability_index(np.ones(100), np.ones(100) * 5) == 0.0


def test_compute_drift_no_shift() -> None:
    rng = np.random.default_rng(1)
    report = compute_drift(frame_from(rng, 0.0), frame_from(rng, 0.0), dt.date(2024, 7, 1))
    assert len(report.features) == len(FEATURE_COLUMNS)
    assert report.share_drifted == 0.0
    assert not report.drifted


def test_compute_drift_full_shift() -> None:
    rng = np.random.default_rng(2)
    report = compute_drift(frame_from(rng, 0.0), frame_from(rng, 3.0), dt.date(2024, 7, 1))
    assert report.share_drifted == 1.0
    assert report.drifted


def test_compute_drift_skips_tiny_samples() -> None:
    rng = np.random.default_rng(3)
    report = compute_drift(
        frame_from(rng, 0.0, n=10), frame_from(rng, 0.0, n=10), dt.date(2024, 7, 1)
    )
    assert report.features == []
    assert report.share_drifted == 0.0
