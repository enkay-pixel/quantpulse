import datetime as dt

import pandas as pd

from quantpulse.data.ingest import (
    BAR_COLUMNS,
    clean_bars,
    normalize_yfinance,
    parse_stooq_csv,
)


def yf_style_frame(tickers: list[str], days: int = 3) -> pd.DataFrame:
    index = pd.date_range("2024-07-01", periods=days, freq="B", name="Date")
    data = {}
    for t in tickers:
        for field, base in [("Open", 100), ("High", 102), ("Low", 99), ("Close", 101)]:
            data[(t, field)] = [base + i for i in range(days)]
        data[(t, "Volume")] = [1_000_000] * days
    return pd.DataFrame(data, index=index)


def test_normalize_yfinance_multiindex() -> None:
    raw = yf_style_frame(["AAPL", "SPY"])
    bars = normalize_yfinance(raw, ["AAPL", "SPY"])
    assert list(bars.columns) == BAR_COLUMNS
    assert set(bars["ticker"]) == {"AAPL", "SPY"}
    assert len(bars) == 6
    assert (bars["source"] == "yfinance").all()
    assert isinstance(bars["date"].iloc[0], dt.date)


def test_normalize_yfinance_skips_missing_ticker() -> None:
    raw = yf_style_frame(["AAPL"])
    bars = normalize_yfinance(raw, ["AAPL", "MISSING"])
    assert set(bars["ticker"]) == {"AAPL"}


def test_parse_stooq_csv_happy_path() -> None:
    text = (
        "Date,Open,High,Low,Close,Volume\n"
        "2024-07-01,100,102,99,101,500000\n"
        "2024-07-02,101,103,100,102,600000\n"
    )
    bars = parse_stooq_csv(text, "AAPL")
    assert len(bars) == 2
    assert (bars["source"] == "stooq").all()
    assert bars["date"].tolist() == [dt.date(2024, 7, 1), dt.date(2024, 7, 2)]


def test_parse_stooq_csv_no_data() -> None:
    assert parse_stooq_csv("No data", "ZZZZ").empty
    assert parse_stooq_csv("", "ZZZZ").empty


def test_clean_bars_drops_invalid_rows_and_duplicates() -> None:
    bars = pd.DataFrame(
        [
            # valid
            ["AAPL", dt.date(2024, 7, 1), 100, 102, 99, 101, 1000, "yfinance"],
            # negative price
            ["AAPL", dt.date(2024, 7, 2), -1, 102, 99, 101, 1000, "yfinance"],
            # high < low
            ["AAPL", dt.date(2024, 7, 3), 100, 98, 99, 101, 1000, "yfinance"],
            # duplicate key (kept: last)
            ["AAPL", dt.date(2024, 7, 1), 200, 202, 199, 201, 2000, "stooq"],
        ],
        columns=BAR_COLUMNS,
    )
    cleaned = clean_bars(bars)
    assert len(cleaned) == 1
    assert cleaned.iloc[0]["source"] == "stooq"
    assert cleaned["volume"].dtype == "int64"
