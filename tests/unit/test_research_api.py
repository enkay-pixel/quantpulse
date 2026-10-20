"""The Research tab's endpoints that need no database: the findings index and the decisions.

The decisions endpoint is judged here with the figures stubbed, because what has to be pinned is
how one decision's conditions combine into the state the page shows — a reopened decision must
never read as standing, and one that cannot be checked must not either.
"""

import datetime as dt
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from quantpulse.api.app import create_app
from quantpulse.api.deps import engine_dep
from quantpulse.monitoring import decisions as dec
from quantpulse.monitoring.decisions import Live, Snapshot

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.chdir(PROJECT_ROOT)  # the settings read configs/ and docs/ relative to here
    app = create_app()
    app.dependency_overrides[engine_dep] = lambda: None
    return TestClient(app)


def test_findings_are_the_index_table_row_for_row(client: TestClient) -> None:
    rows = [
        line
        for line in (PROJECT_ROOT / "docs/findings/README.md").read_text().splitlines()
        if line.startswith("| [")
    ]
    findings = client.get("/findings").json()["findings"]
    assert len(findings) == len(rows), "a row of the findings index was dropped"
    assert all(f["url"].startswith("https://github.com/") for f in findings)
    assert not any("**" in f["outcome"] or "](" in f["outcome"] for f in findings), (
        "markdown leaked into an outcome"
    )


def test_each_decision_reads_as_its_worst_condition(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    snapshot = Snapshot(
        # XJSE live Sharpe below zero fires `keep-jse-model`, whatever else it watches.
        live={"XJSE": Live(61, -0.1, 0.3, dt.date(2026, 10, 20)), "XNYS": Live(65, 1.0, 0.8, None)},
        promotions={},
        option_snapshot_days=60,
        verdicts=None,  # the verdict directory not visible: that condition is unknown
    )
    monkeypatch.setattr(dec, "collect", lambda engine, verdict_dir: snapshot)
    states = {d["id"]: d["state"] for d in client.get("/decisions").json()["decisions"]}
    assert states["keep-jse-model"] == "reopened", "a fired condition did not reopen it"
    assert states["fixed-defaults-by-shadow"] == "unknown", "an unseen verdict read as standing"
    assert states["no-nyse-pruning"] == "manual"
    assert states["options-descriptive-only"] == "standing"
