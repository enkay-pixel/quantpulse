"""The research watchlist's file (ADR 0007): validated on load, and never naming a model ticker."""

from pathlib import Path

import pytest

from quantpulse.data.universe import load_universe
from quantpulse.research.watchlist import WatchlistError, load_watchlist

ROOT = Path(__file__).resolve().parents[2]


def _write(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "watchlist.yaml"
    path.write_text(body)
    return path


def test_the_shipped_watchlist_loads_and_names_no_universe_ticker() -> None:
    """The sync refuses an overlap at run time; this catches it before a commit reaches the
    evening run, since following a name twice would blur which numbers are the model's."""
    names = load_watchlist(ROOT / "configs" / "watchlist.yaml")
    universe = {e.ticker for e in load_universe(ROOT / "configs" / "universe.yaml")}
    assert names, "the shipped watchlist is empty — the page would show nothing to compare"
    assert not {n.ticker for n in names} & universe


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ("names:\n  - {ticker: GME, exchange: XNAS, why: x}\n", "exchange must be one of"),
        ("names:\n  - {ticker: GME, exchange: XNYS}\n", "say why"),
        ("names:\n  - {ticker: GME, exchange: XNYS, asset_type: bond, why: x}\n", "asset_type"),
        (
            "names:\n  - {ticker: GME, exchange: XNYS, why: x}\n"
            "  - {ticker: GME, exchange: XNYS, why: y}\n",
            "more than once",
        ),
        ("names:\n  - {exchange: XNYS, why: x}\n", "no ticker"),
    ],
)
def test_a_malformed_entry_is_refused_by_name(tmp_path: Path, body: str, message: str) -> None:
    with pytest.raises(WatchlistError, match=message):
        load_watchlist(_write(tmp_path, body))


def test_an_empty_file_is_an_empty_watchlist(tmp_path: Path) -> None:
    assert load_watchlist(_write(tmp_path, "")) == []


def test_only_us_names_count_as_optioned(tmp_path: Path) -> None:
    names = load_watchlist(
        _write(
            tmp_path,
            "names:\n  - {ticker: GME, exchange: XNYS, why: x}\n"
            "  - {ticker: MTN.JO, exchange: XJSE, why: y}\n",
        )
    )
    assert [n.ticker for n in names if n.has_options] == ["GME"]
