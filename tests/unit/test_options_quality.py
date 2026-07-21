import pandas as pd

from quantpulse.data.quality import failed_checks
from quantpulse.options.quality import run_option_quality_checks


def quotes(n_tickers: int = 10, iv: float = 0.30, open_interest: int = 100) -> pd.DataFrame:
    rows = []
    for i in range(n_tickers):
        for strike in (90.0, 100.0, 110.0):
            rows.append(
                {
                    "ticker": f"T{i}",
                    "implied_volatility": iv,
                    "open_interest": open_interest,
                    "delta": 0.5,
                    "gamma": 0.02,
                    "theta": -0.01,
                    "vega": 0.1,
                    "theo_value": 5.0 + strike / 100,
                }
            )
    return pd.DataFrame(rows)


def test_healthy_snapshot_passes_everything() -> None:
    assert failed_checks(run_option_quality_checks(quotes(), 10)) == []


def test_empty_snapshot_fails_fast() -> None:
    results = run_option_quality_checks(pd.DataFrame(), 10)
    assert [r.name for r in failed_checks(results)] == ["non_empty"]


def test_stale_premarket_iv_is_flagged() -> None:
    """The empirical failure mode: ~2% median IV from untraded contracts."""
    results = run_option_quality_checks(quotes(iv=0.02), 10)
    failed = {r.name for r in failed_checks(results)}
    assert "implied_vol_plausible" in failed


def test_absurdly_high_iv_is_flagged() -> None:
    failed = {r.name for r in failed_checks(run_option_quality_checks(quotes(iv=5.0), 10))}
    assert "implied_vol_plausible" in failed


def test_thin_ticker_coverage_is_flagged() -> None:
    failed = {r.name for r in failed_checks(run_option_quality_checks(quotes(n_tickers=4), 50))}
    assert "ticker_coverage" in failed


def test_no_traded_contracts_is_flagged() -> None:
    failed = {r.name for r in failed_checks(run_option_quality_checks(quotes(open_interest=0), 10))}
    assert "has_traded_contracts" in failed


def test_missing_greeks_are_flagged() -> None:
    frame = quotes()
    frame.loc[0, "delta"] = None
    failed = {r.name for r in failed_checks(run_option_quality_checks(frame, 10))}
    assert "greeks_present" in failed
