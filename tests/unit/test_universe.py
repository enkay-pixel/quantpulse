from pathlib import Path
from typing import cast

import pytest
from sqlalchemy.orm import Session

from quantpulse.data import universe as universe_mod
from quantpulse.data.calendar import EXCHANGES
from quantpulse.data.universe import load_universe, options_tickers


def write_universe(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "universe.yaml"
    path.write_text(content)
    return path


def test_load_universe_parses_types_and_uppercases(tmp_path: Path) -> None:
    path = write_universe(tmp_path, "etfs:\n  - spy\nstocks:\n  - AAPL\n  - msft\n")
    entries = load_universe(path)
    assert {(e.ticker, e.asset_type) for e in entries} == {
        ("SPY", "etf"),
        ("AAPL", "stock"),
        ("MSFT", "stock"),
    }


def test_load_universe_rejects_duplicates(tmp_path: Path) -> None:
    path = write_universe(tmp_path, "etfs:\n  - SPY\nstocks:\n  - SPY\n")
    with pytest.raises(ValueError, match="Duplicate"):
        load_universe(path)


def test_load_universe_rejects_empty(tmp_path: Path) -> None:
    path = write_universe(tmp_path, "etfs: []\nstocks: []\n")
    with pytest.raises(ValueError, match="no tickers"):
        load_universe(path)


def test_repo_universe_file_is_valid() -> None:
    repo_file = Path(__file__).parents[2] / "configs" / "universe.yaml"
    entries = load_universe(repo_file)
    assert len(entries) >= 40


# --- options_tickers ----------------------------------------------------------------
#
# The single place that answers "which markets have chains to snapshot?". The CLI, the
# option_chains asset, and its quality check all narrow through it; they used to each
# carry their own copy of the rule, and the CLI's copy was missing entirely.


@pytest.fixture
def recorded_exchanges(monkeypatch: pytest.MonkeyPatch) -> list[str | None]:
    """Capture which exchange codes get queried, without needing a database."""
    asked: list[str | None] = []

    def fake_active_tickers(session: Session, exchange: str | None = None) -> list[str]:
        asked.append(exchange)
        return [f"{exchange}-A", f"{exchange}-B"]

    monkeypatch.setattr(universe_mod, "active_tickers", fake_active_tickers)
    return asked


#: A stand-in session — the stubbed active_tickers never touches it.
NO_SESSION = cast(Session, object())


def test_options_tickers_skips_markets_without_chains(
    recorded_exchanges: list[str | None],
) -> None:
    """The bug this guards: the CLI passed the whole universe, JSE names included."""
    tickers = options_tickers(NO_SESSION)

    assert "XJSE" not in recorded_exchanges  # no free JSE chain data exists
    assert recorded_exchanges == ["XNYS"]
    assert tickers == ["XNYS-A", "XNYS-B"]


def test_options_tickers_covers_every_options_bearing_market(
    recorded_exchanges: list[str | None],
) -> None:
    """Derived from the registry, so a market that gains `has_options` is picked up."""
    options_tickers(NO_SESSION)

    assert set(recorded_exchanges) == {c for c, e in EXCHANGES.items() if e.has_options}
