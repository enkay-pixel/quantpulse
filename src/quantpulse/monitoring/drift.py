"""Feature drift detection.

The *decision* metrics (KS test + PSI per feature) are computed here with scipy so the
retraining trigger rests on small, tested code. An Evidently HTML report is generated
best-effort as a human-readable diagnostic artifact.
"""

import datetime as dt
import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from quantpulse.db import DriftMetric
from quantpulse.features.engineering import FEATURE_COLUMNS, FEATURE_VERSION
from quantpulse.features.store import load_features

logger = logging.getLogger(__name__)

PSI_DRIFT_THRESHOLD = 0.2  # per-feature: PSI above this counts as drifted
SHARE_DRIFT_THRESHOLD = 0.3  # overall: retrain when this share of features drifted
REFERENCE_DAYS = 252  # ~1 trading year of reference history
CURRENT_DAYS = 30  # recent window under test


@dataclass(frozen=True)
class FeatureDrift:
    feature: str
    ks_statistic: float
    ks_pvalue: float
    psi: float
    drifted: bool


@dataclass(frozen=True)
class DriftReport:
    asof: dt.date
    features: list[FeatureDrift]
    share_drifted: float

    @property
    def drifted(self) -> bool:
        return self.share_drifted >= SHARE_DRIFT_THRESHOLD


def population_stability_index(reference: np.ndarray, current: np.ndarray, bins: int = 10) -> float:
    """PSI over quantile bins of the reference distribution."""
    quantiles = np.quantile(reference, np.linspace(0, 1, bins + 1))
    quantiles[0], quantiles[-1] = -np.inf, np.inf
    edges = np.unique(quantiles)
    if len(edges) < 3:  # degenerate (near-constant) reference
        return 0.0
    ref_counts, _ = np.histogram(reference, bins=edges)
    cur_counts, _ = np.histogram(current, bins=edges)
    ref_pct = np.clip(ref_counts / max(len(reference), 1), 1e-6, None)
    cur_pct = np.clip(cur_counts / max(len(current), 1), 1e-6, None)
    return float(np.sum((cur_pct - ref_pct) * np.log(cur_pct / ref_pct)))


def compute_drift(reference: pd.DataFrame, current: pd.DataFrame, asof: dt.date) -> DriftReport:
    results: list[FeatureDrift] = []
    for col in FEATURE_COLUMNS:
        ref = reference[col].dropna().to_numpy()
        cur = current[col].dropna().to_numpy()
        if len(ref) < 30 or len(cur) < 30:
            continue
        ks = stats.ks_2samp(ref, cur)
        psi = population_stability_index(ref, cur)
        results.append(
            FeatureDrift(
                feature=col,
                ks_statistic=float(ks.statistic),
                ks_pvalue=float(ks.pvalue),
                psi=psi,
                drifted=psi > PSI_DRIFT_THRESHOLD,
            )
        )
    share = float(np.mean([r.drifted for r in results])) if results else 0.0
    return DriftReport(asof=asof, features=results, share_drifted=share)


def store_drift_report(session: Session, report: DriftReport) -> int:
    rows = [
        DriftMetric(
            date=report.asof,
            feature_version=FEATURE_VERSION,
            metric_name=f"psi:{f.feature}",
            value=f.psi,
            drifted=f.drifted,
        )
        for f in report.features
    ]
    rows.append(
        DriftMetric(
            date=report.asof,
            feature_version=FEATURE_VERSION,
            metric_name="share_drifted",
            value=report.share_drifted,
            drifted=report.drifted,
        )
    )
    session.add_all(rows)
    return len(rows)


def run_drift_check(engine: Engine, session: Session, asof: dt.date | None = None) -> DriftReport:
    """Compare the recent feature window against the reference history and persist results."""
    features = load_features(engine, FEATURE_VERSION)
    if features.empty:
        raise ValueError("No stored features — run the feature pipeline first")
    dates = sorted(features["date"].unique())
    asof = asof or dates[-1]
    current_start = dates[max(0, len(dates) - CURRENT_DAYS)]
    reference = features[features["date"] < current_start].tail(REFERENCE_DAYS * 100)
    current = features[features["date"] >= current_start]
    report = compute_drift(reference, current, asof)
    store_drift_report(session, report)
    logger.info(
        "Drift check %s: %d features, share_drifted=%.2f (drifted=%s)",
        asof,
        len(report.features),
        report.share_drifted,
        report.drifted,
    )
    return report


def write_evidently_report(
    reference: pd.DataFrame, current: pd.DataFrame, output_path: Path
) -> bool:
    """Best-effort human-readable drift report; never fails the pipeline."""
    try:
        from evidently import Report
        from evidently.presets import DataDriftPreset

        report = Report([DataDriftPreset()])
        snapshot = report.run(
            current_data=current[list(FEATURE_COLUMNS)],
            reference_data=reference[list(FEATURE_COLUMNS)],
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        snapshot.save_html(str(output_path))
        return True
    except Exception:  # pragma: no cover - diagnostic only
        logger.warning("Evidently report generation failed", exc_info=True)
        return False
