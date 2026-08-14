"""Failure alerts.

Failures are recorded in Postgres (`pipeline_alerts`) and surfaced by the API, so the
dashboard can show "something broke" without any paid notification service. On macOS a
desktop notification is also attempted best-effort (no-op inside containers).

**Why Postgres and not a file.** This used to append to JSONL under `DAGSTER_HOME`. The
Dagster daemon writes alerts and the API serves them from a *different container*, and
that path is neither a shared volume nor persistent — it lives in the daemon's writable
layer, so the API could never read it and `compose up` erased it. Real failures were
recorded perfectly and still surfaced as an empty `/alerts`. The database is the one
durable thing both containers already share.

Recording an alert must never take down the run that is already failing, so every
database error here is swallowed and logged.
"""

import contextlib
import datetime as dt
import logging
import shutil
import subprocess

from sqlalchemy import delete, select
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)

#: Keep the alert log bounded — this is an operational tail, not an audit trail.
MAX_ALERTS = 200


def record_failure(job_name: str, run_id: str, error: str) -> None:
    """Record a failure, trimming the log so it cannot grow without bound."""
    from quantpulse.db import PipelineAlert, get_session

    try:
        with get_session() as session:
            session.add(PipelineAlert(job_name=job_name, run_id=run_id, error=error[:500]))
            session.flush()
            # Trim by id: monotonic, and unlike created_at it cannot tie.
            keep_from = session.scalars(
                select(PipelineAlert.id).order_by(PipelineAlert.id.desc()).limit(MAX_ALERTS)
            ).all()
            if len(keep_from) == MAX_ALERTS:
                session.execute(delete(PipelineAlert).where(PipelineAlert.id < min(keep_from)))
            session.commit()
    except SQLAlchemyError:
        # The pipeline is already failing; a broken alert write must not mask the cause.
        logger.warning("Could not record alert for %s", job_name, exc_info=True)

    _notify_macos(f"QuantPulse: {job_name} failed", error[:200])


def read_alerts(limit: int | None = None) -> list[dict[str, str]]:
    """Most-recent-last failure records; empty when nothing has ever failed."""
    from quantpulse.db import PipelineAlert, get_session

    try:
        with get_session() as session:
            stmt = select(PipelineAlert).order_by(PipelineAlert.id.desc())
            if limit:
                stmt = stmt.limit(limit)
            rows = list(session.scalars(stmt).all())
            return [
                {
                    "timestamp": _isoformat(row.created_at),
                    "job_name": row.job_name,
                    "run_id": row.run_id or "",
                    "error": row.error,
                }
                for row in reversed(rows)  # newest last, as the API contract promises
            ]
    except SQLAlchemyError:
        # A dashboard that cannot reach the database should say "no alerts", not 500.
        logger.warning("Could not read alerts", exc_info=True)
        return []


def _isoformat(value: dt.datetime | None) -> str:
    if value is None:  # pragma: no cover - server_default always populates this
        return ""
    # Rows written before the column had a timezone-aware default read back naive.
    return (value if value.tzinfo else value.replace(tzinfo=dt.UTC)).isoformat()


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
