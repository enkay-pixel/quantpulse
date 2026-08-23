"""Vectorized feature engineering over long-format daily bars.

Input frames carry at least: ticker, date, close, volume.
All rolling windows are trailing-only — nothing here can see the future; the only
forward-looking column is the explicit `fwd_ret` target built by `make_forward_returns`.
"""

import numpy as np
import pandas as pd

FEATURE_VERSION = "v1"

# Per-ticker technical features (trailing windows)
_TECHNICAL = [
    "ret_1",
    "ret_5",
    "ret_21",
    "mom_63",
    "vol_21",
    "vol_63",
    "ma_ratio_21",
    "ma_ratio_63",
    "volume_z_21",
]
# Cross-sectional (per-date) transforms applied to these columns
_CROSS_SECTIONAL_BASE = ["ret_5", "ret_21", "mom_63", "ma_ratio_21"]

FEATURE_COLUMNS = _TECHNICAL + [f"{c}_cs_rank" for c in _CROSS_SECTIONAL_BASE]

#: The supervised label built by `make_forward_returns`. Named once so training,
#: baselines and any future consumer cannot disagree about it — a test fixture that
#: invented its own name passed 16 green tests and failed on the first real frame.
LABEL_COLUMN = "fwd_ret"


def compute_features(bars: pd.DataFrame) -> pd.DataFrame:
    """Return a (ticker, date) frame with FEATURE_COLUMNS, NaN warm-up rows dropped.

    If `bars` carries an `exchange` column, cross-sectional ranks are computed **within**
    each exchange. This is not cosmetic: ranking every ticker against every other on a date
    would compare Naspers to Apple — different currency, different session, different macro
    — and the ranks would degrade into noise without anything failing.
    """
    columns = ["ticker", "date", "close", "volume"]
    has_exchange = "exchange" in bars.columns
    if has_exchange:
        columns.append("exchange")
    df = bars[columns].sort_values(["ticker", "date"]).copy()
    grouped = df.groupby("ticker", group_keys=False)

    df["ret_1"] = grouped["close"].pct_change(1, fill_method=None)
    df["ret_5"] = grouped["close"].pct_change(5, fill_method=None)
    df["ret_21"] = grouped["close"].pct_change(21, fill_method=None)
    df["mom_63"] = grouped["close"].pct_change(63, fill_method=None)

    df["vol_21"] = grouped["ret_1"].transform(lambda s: s.rolling(21).std())
    df["vol_63"] = grouped["ret_1"].transform(lambda s: s.rolling(63).std())

    df["ma_ratio_21"] = df["close"] / grouped["close"].transform(lambda s: s.rolling(21).mean()) - 1
    df["ma_ratio_63"] = df["close"] / grouped["close"].transform(lambda s: s.rolling(63).mean()) - 1

    log_volume = np.log1p(df["volume"].astype("float64"))
    df["_log_vol"] = log_volume
    df["volume_z_21"] = grouped["_log_vol"].transform(
        lambda s: (s - s.rolling(21).mean()) / (s.rolling(21).std() + 1e-9)
    )
    df = df.drop(columns=["_log_vol"])

    cross_section = ["date", "exchange"] if has_exchange else ["date"]
    for col in _CROSS_SECTIONAL_BASE:
        df[f"{col}_cs_rank"] = df.groupby(cross_section)[col].rank(pct=True)

    df = df.dropna(subset=FEATURE_COLUMNS)
    return df[["ticker", "date", *FEATURE_COLUMNS]].reset_index(drop=True)


def make_forward_returns(bars: pd.DataFrame, horizon: int) -> pd.DataFrame:
    """Target: `horizon`-day forward return per (ticker, date). Rows without a future drop out."""
    df = bars[["ticker", "date", "close"]].sort_values(["ticker", "date"]).copy()
    grouped = df.groupby("ticker", group_keys=False)
    df["fwd_ret"] = grouped["close"].shift(-horizon) / df["close"] - 1
    return df.dropna(subset=["fwd_ret"])[["ticker", "date", "fwd_ret"]].reset_index(drop=True)


def build_training_frame(features: pd.DataFrame, targets: pd.DataFrame) -> pd.DataFrame:
    """Inner-join features and targets on (ticker, date)."""
    frame = features.merge(targets, on=["ticker", "date"], how="inner")
    return frame.sort_values(["date", "ticker"]).reset_index(drop=True)


def feature_columns_for(exchange: str | None = None) -> list[str]:
    """The columns one market trains on, defaulting to all engineered features.

    Validated rather than trusted: a name that is not an engineered column is a typo, and
    silently dropping it would train a shorter model that still fits, still scores and still
    reports a number — the failure would surface as a worse model weeks later, attributed to
    anything but a misspelling.
    """
    from quantpulse.data.calendar import get_exchange

    chosen = get_exchange(exchange).feature_columns
    if not chosen:
        return list(FEATURE_COLUMNS)
    unknown = [c for c in chosen if c not in FEATURE_COLUMNS]
    if unknown:
        raise ValueError(
            f"{get_exchange(exchange).code} names features that are not engineered: "
            f"{unknown}; known: {sorted(FEATURE_COLUMNS)}"
        )
    return list(chosen)
