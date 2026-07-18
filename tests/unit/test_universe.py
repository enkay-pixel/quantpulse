from pathlib import Path

import pytest

from quantpulse.data.universe import load_universe


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
