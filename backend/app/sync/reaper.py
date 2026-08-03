"""Stale-run reaper (design.md, "Self-healing property"): marks any
`sync_runs` row stuck `running` past a heartbeat staleness threshold as
`abandoned`. Invoked opportunistically — at the head of `POST /api/sync`
(see `app/sync/service.py::trigger_sync`, formerly `begin_sync`) — rather
than as a separate cron/scheduled process, since this system has none
(design.md, "No scheduler").
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.store.models import SyncRun

#: design.md: "a stale-run reaper marks any run whose heartbeat_at is
#: older than 5 minutes as abandoned".
STALE_AFTER: dt.timedelta = dt.timedelta(minutes=5)


def reap_abandoned_runs(
    session: Session,
    *,
    now: dt.datetime | None = None,
    stale_after: dt.timedelta = STALE_AFTER,
) -> int:
    """Marks every `running` run whose `heartbeat_at` is older than
    `stale_after` as `abandoned`. Returns the number of runs reaped.
    Caller is responsible for `session.commit()`."""
    now = now or dt.datetime.now(dt.timezone.utc)
    cutoff = now - stale_after

    stale_runs = list(
        session.scalars(
            select(SyncRun).where(
                SyncRun.status == "running", SyncRun.heartbeat_at < cutoff
            )
        )
    )
    for run in stale_runs:
        run.status = "abandoned"
        run.completed_at = now
        run.error = run.error or "reaped: no heartbeat within staleness threshold"

    if stale_runs:
        session.flush()
    return len(stale_runs)
