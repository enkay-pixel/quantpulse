"""Failure alerts.

Deliberately dependency-free and local: failures are appended to a JSONL file inside the
Dagster home volume and surfaced by the API, so the dashboard can show "something broke"
without any paid notification service. On macOS a desktop notification is also attempted
best-effort (no-op inside containers).
"""

import contextlib
import datetime as dt
import json
import logging
import os
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

MAX_ALERTS = 200


def alerts_path() -> Path:
    """JSONL alert log; lives in DAGSTER_HOME when set so it survives container restarts."""
    base = Path(os.environ.get("DAGSTER_HOME", "/tmp"))
    return base / "alerts.jsonl"


def record_failure(job_name: str, run_id: str, error: str) -> None:
    """Append a failure record, trimming the log so it can't grow without bound."""
    entry = {
        "timestamp": dt.datetime.now(dt.UTC).isoformat(),
        "job_name": job_name,
        "run_id": run_id,
        "error": error[:500],
    }
    path = alerts_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        existing = read_alerts()
        existing.append(entry)
        with path.open("w") as fh:
            for record in existing[-MAX_ALERTS:]:
                fh.write(json.dumps(record) + "\n")
    except OSError:
        logger.warning("Could not write alert log at %s", path, exc_info=True)

    _notify_macos(f"QuantPulse: {job_name} failed", error[:200])


def read_alerts(limit: int | None = None) -> list[dict[str, str]]:
    """Most-recent-last failure records; empty when nothing has ever failed."""
    path = alerts_path()
    if not path.exists():
        return []
    records: list[dict[str, str]] = []
    try:
        for line in path.read_text().splitlines():
            if line.strip():
                records.append(json.loads(line))
    except (OSError, json.JSONDecodeError):
        logger.warning("Could not read alert log at %s", path, exc_info=True)
        return []
    return records[-limit:] if limit else records


def _notify_macos(title: str, message: str) -> None:
    """Best-effort desktop notification; silently absent in containers."""
    osascript = shutil.which("osascript")
    if not osascript:
        return
    safe = message.replace('"', "'")
    with contextlib.suppress(OSError, subprocess.SubprocessError):  # cosmetic only
        subprocess.run(
            [osascript, "-e", f'display notification "{safe}" with title "{title}"'],
            check=False,
            timeout=5,
        )
