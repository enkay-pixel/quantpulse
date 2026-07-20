import datetime as dt

import pandas as pd

from quantpulse.options.ingest import _rows_for_ticker


def chain_frame(strikes: list[float], itm_below: float) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "strike": strikes,
            "bid": [1.0] * len(strikes),
            "ask": [1.2] * len(strikes),
            "lastPrice": [1.1] * len(strikes),
            "volume": [10] * len(strikes),
            "openInterest": [100] * len(strikes),
            "impliedVolatility": [0.3] * len(strikes),
            "inTheMoney": [s < itm_below for s in strikes],
        }
    )


def test_rows_respect_moneyness_bound_and_compute_greeks() -> None:
    spot = 100.0
    strikes = [70, 85, 100, 115, 130, 150]  # ±20% keeps 85..115
    calls = chain_frame(strikes, itm_below=spot)
    puts = chain_frame(strikes, itm_below=spot)
    chains = [(dt.date(2026, 8, 21), calls, puts)]

    rows = _rows_for_ticker("AAPL", spot, chains, dt.date(2026, 7, 20), moneyness=0.2, rate=0.04)

    kept = {r["strike"] for r in rows}
    assert kept == {85.0, 100.0, 115.0}  # 70, 130, 150 filtered out
    assert len(rows) == 6  # 3 strikes x call+put

    call_atm = next(r for r in rows if r["option_type"] == "call" and r["strike"] == 100.0)
    put_atm = next(r for r in rows if r["option_type"] == "put" and r["strike"] == 100.0)
    assert 0 < call_atm["delta"] < 1
    assert -1 < put_atm["delta"] < 0
    assert call_atm["gamma"] > 0
    assert call_atm["theo_value"] > 0
    assert call_atm["open_interest"] == 100


def test_empty_when_no_strikes_in_band() -> None:
    calls = chain_frame([50, 200], itm_below=100)
    chains = [(dt.date(2026, 8, 21), calls, calls)]
    rows = _rows_for_ticker("X", 100.0, chains, dt.date(2026, 7, 20), moneyness=0.2, rate=0.04)
    assert rows == []
