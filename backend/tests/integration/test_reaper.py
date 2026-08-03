"""Integration tests for `app.sync.reaper` — marks a `sync_runs` row
`abandoned` when its `heartbeat_at` goes stale, self-healing after a
spun-down Render instance kills a run mid-sync (design.md, "Self-healing
property"). Invoked opportunistically (startup + head of every
`POST /api/sync`), not a separate cron process — there is no scheduler in
this system (design.md, "No scheduler").
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.store.models import Base, SyncRun
from app.sync.reaper import STALE_AFTER, reap_abandoned_runs


@pytest.fixture()
def session(postgres_container: str) -> Iterator[Session]:
    engine = create_engine(postgres_container)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    Base.metadata.drop_all(engine)
    engine.dispose()


def test_stale_running_run_is_marked_abandoned(session: Session) -> None:
    now = dt.datetime(2026, 3, 1, 12, 0, tzinfo=dt.timezone.utc)
    stale_heartbeat = now - STALE_AFTER - dt.timedelta(seconds=1)
    run = SyncRun(status="running", started_at=stale_heartbeat, heartbeat_at=stale_heartbeat)
    session.add(run)
    session.commit()

    reaped = reap_abandoned_runs(session, now=now)
    session.commit()

    assert reaped == 1
    refreshed = session.get(SyncRun, run.id)
    assert refreshed is not None
    assert refreshed.status == "abandoned"
    assert refreshed.completed_at == now
    assert refreshed.error is not None


def test_fresh_heartbeat_running_run_is_left_alone(session: Session) -> None:
    now = dt.datetime(2026, 3, 1, 12, 0, tzinfo=dt.timezone.utc)
    fresh_heartbeat = now - dt.timedelta(seconds=30)
    run = SyncRun(status="running", started_at=fresh_heartbeat, heartbeat_at=fresh_heartbeat)
    session.add(run)
    session.commit()

    reaped = reap_abandoned_runs(session, now=now)

    assert reaped == 0
    refreshed = session.get(SyncRun, run.id)
    assert refreshed is not None
    assert refreshed.status == "running"


def test_already_completed_run_is_never_touched_even_if_old(session: Session) -> None:
    now = dt.datetime(2026, 3, 1, 12, 0, tzinfo=dt.timezone.utc)
    ancient = now - dt.timedelta(days=30)
    run = SyncRun(
        status="completed", started_at=ancient, heartbeat_at=ancient, completed_at=ancient
    )
    session.add(run)
    session.commit()

    reaped = reap_abandoned_runs(session, now=now)

    assert reaped == 0
    refreshed = session.get(SyncRun, run.id)
    assert refreshed is not None
    assert refreshed.status == "completed"
