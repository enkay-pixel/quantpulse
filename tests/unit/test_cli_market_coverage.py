"""CLI commands that act per market must cover every market unless told otherwise.

`train_evaluate_promote` handles one market and defaults to the NYSE. A caller that omits
the exchange therefore trains half the platform and prints a summary that reads like a full
retrain — no error, no warning, and the missing market only shows up as an absent row in
`model_runs` days later. The scheduled Dagster path loops markets itself, so the two
disagreed about what "train" meant.
"""

import pytest

from quantpulse import cli
from quantpulse.data.calendar import EXCHANGES


@pytest.fixture
def trained(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    """Record which markets a CLI call trains, without touching a database or a model."""
    calls: list[str] = []

    class _Session:
        def __enter__(self):  # type: ignore[no-untyped-def]
            return self

        def __exit__(self, *exc):  # type: ignore[no-untyped-def]
            return False

    monkeypatch.setattr("quantpulse.db.get_session", lambda *a, **k: _Session())
    monkeypatch.setattr("quantpulse.db.get_engine", lambda *a, **k: object())
    monkeypatch.setattr("quantpulse.data.universe.active_tickers", lambda *a, **k: ["AAA"])

    def fake_train(engine, session, *, tracking_uri=None, exchange, **kw):  # type: ignore[no-untyped-def]
        calls.append(exchange)
        return {"exchange": exchange, "promoted": False}

    monkeypatch.setattr("quantpulse.ml.pipeline.train_evaluate_promote", fake_train)
    return calls


def test_train_without_an_exchange_covers_every_market(trained) -> None:  # type: ignore[no-untyped-def]
    cli._train(None)
    assert sorted(trained) == sorted(EXCHANGES)


def test_train_can_still_be_narrowed_to_one_market(trained) -> None:  # type: ignore[no-untyped-def]
    cli._train("XJSE")
    assert trained == ["XJSE"]


def test_a_market_with_no_universe_is_skipped_not_trained(  # type: ignore[no-untyped-def]
    trained, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Training a market with no tickers would spend an Optuna budget to fit nothing."""
    monkeypatch.setattr(
        "quantpulse.data.universe.active_tickers",
        lambda session, code, *a, **k: [] if code == "XJSE" else ["AAA"],
    )
    cli._train(None)
    assert "XJSE" not in trained
    assert "XNYS" in trained


def test_the_train_command_accepts_an_exchange_flag() -> None:
    """Without the flag the only way to run one market is to run both."""
    parser_argv = ["train", "--exchange", "XJSE"]
    # argparse raises SystemExit(2) on an unrecognized argument.
    import contextlib
    import io

    err = io.StringIO()
    with contextlib.redirect_stderr(err), pytest.raises(SystemExit) as exc:
        cli.main([*parser_argv, "--nonsense"])
    assert exc.value.code == 2  # rejected for --nonsense, not for --exchange
    assert "--exchange" not in err.getvalue()
