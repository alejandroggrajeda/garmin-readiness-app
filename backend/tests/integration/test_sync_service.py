"""Integration tests for `app.sync.service` — the manual sync orchestrator.
Real ephemeral Postgres (`testcontainers`) for the advisory lock, `sync_runs`
and `garmin_session` rows; `FakeGarminGateway` (never live Garmin) for the
data source, per garmin-sync's Manual Sync / Auth-Failure / Credential
Security requirements and design.md's auth-failure circuit breaker table.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.garmin.fake import FakeGarminGateway
from app.store.models import Base, DailyMetric, GarminSession, SyncRun
from app.sync.lock import try_acquire_lock
from app.sync.service import (
    MAX_DAYS_PER_RUN,
    SyncAlreadyRunning,
    SyncAuthLocked,
    SyncCooldown,
    SyncStarted,
    begin_sync,
    execute_and_release,
)

NOW = dt.datetime(2026, 3, 15, 9, 0, tzinfo=dt.timezone.utc)


@pytest.fixture()
def session(postgres_container: str) -> Iterator[Session]:
    engine = create_engine(postgres_container)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    Base.metadata.drop_all(engine)
    engine.dispose()


def test_begin_sync_while_idle_starts_a_run_and_holds_the_lock(session: Session) -> None:
    result = begin_sync(session, gateway=FakeGarminGateway(), now=NOW)

    assert isinstance(result, SyncStarted)
    run = session.get(SyncRun, result.run_id)
    assert run is not None
    assert run.status == "running"
    # `session` itself now holds the advisory lock (begin_sync acquired it).
    with Session(session.bind) as other:
        assert try_acquire_lock(other) is False


def test_begin_sync_while_another_run_holds_the_lock_returns_409_shape(
    session: Session,
) -> None:
    first = begin_sync(session, gateway=FakeGarminGateway(), now=NOW)
    assert isinstance(first, SyncStarted)

    with Session(session.bind) as other_session:
        second = begin_sync(other_session, gateway=FakeGarminGateway(), now=NOW)

    assert isinstance(second, SyncAlreadyRunning)
    assert second.run_id == first.run_id


def test_execute_and_release_success_writes_metrics_completes_run_and_frees_lock(
    session: Session,
) -> None:
    started = begin_sync(session, gateway=FakeGarminGateway(), now=NOW)
    assert isinstance(started, SyncStarted)

    execute_and_release(
        session, started.run_id, gateway=FakeGarminGateway(), now=NOW
    )

    run = session.get(SyncRun, started.run_id)
    assert run is not None
    assert run.status == "completed"
    assert run.completed_at is not None

    metrics = session.query(DailyMetric).all()
    assert len(metrics) == MAX_DAYS_PER_RUN
    assert all(m.source_run_id == run.id for m in metrics)

    with Session(session.bind) as other:
        assert try_acquire_lock(other) is True  # lock was released


def test_execute_and_release_auth_failure_is_non_fatal_and_locks_the_breaker(
    session: Session,
) -> None:
    started = begin_sync(session, gateway=FakeGarminGateway(), now=NOW)
    assert isinstance(started, SyncStarted)

    # non-fatal: must not raise
    execute_and_release(
        session,
        started.run_id,
        gateway=FakeGarminGateway(auth_error=True),
        now=NOW,
    )

    run = session.get(SyncRun, started.run_id)
    assert run is not None
    assert run.status == "failed"
    assert run.error is not None and "auth" in run.error

    breaker = session.get(GarminSession, 1)
    assert breaker is not None
    assert breaker.auth_locked is True

    with Session(session.bind) as other:
        assert try_acquire_lock(other) is True  # lock still freed on failure


def test_subsequent_sync_is_locked_out_after_an_auth_failure(session: Session) -> None:
    started = begin_sync(session, gateway=FakeGarminGateway(), now=NOW)
    assert isinstance(started, SyncStarted)
    execute_and_release(
        session, started.run_id, gateway=FakeGarminGateway(auth_error=True), now=NOW
    )

    next_attempt = begin_sync(session, gateway=FakeGarminGateway(), now=NOW)

    assert isinstance(next_attempt, SyncAuthLocked)


def test_rate_limit_sets_a_six_hour_cooldown_that_blocks_new_syncs(
    session: Session,
) -> None:
    started = begin_sync(session, gateway=FakeGarminGateway(), now=NOW)
    assert isinstance(started, SyncStarted)
    execute_and_release(
        session, started.run_id, gateway=FakeGarminGateway(rate_limited=True), now=NOW
    )

    soon_after = NOW + dt.timedelta(hours=1)
    blocked = begin_sync(session, gateway=FakeGarminGateway(), now=soon_after)
    assert isinstance(blocked, SyncCooldown)
    assert blocked.retry_after_seconds > 0

    after_cooldown = NOW + dt.timedelta(hours=6, minutes=1)
    allowed = begin_sync(session, gateway=FakeGarminGateway(), now=after_cooldown)
    assert isinstance(allowed, SyncStarted)


def test_network_failure_after_retries_abandons_the_run_non_fatally(
    session: Session,
) -> None:
    started = begin_sync(session, gateway=FakeGarminGateway(), now=NOW)
    assert isinstance(started, SyncStarted)

    execute_and_release(
        session,
        started.run_id,
        gateway=FakeGarminGateway(network_error=True),
        now=NOW,
        sleep=lambda _seconds: None,
    )

    run = session.get(SyncRun, started.run_id)
    assert run is not None
    assert run.status == "abandoned"

    with Session(session.bind) as other:
        assert try_acquire_lock(other) is True  # never left stuck locked


def test_reaper_runs_opportunistically_at_the_head_of_begin_sync(
    session: Session,
) -> None:
    """An orphaned `running` row from a killed instance must not block a
    brand-new sync forever — `begin_sync` reaps it first."""
    stale = NOW - dt.timedelta(minutes=10)
    orphan = SyncRun(status="running", started_at=stale, heartbeat_at=stale)
    session.add(orphan)
    session.commit()

    result = begin_sync(session, gateway=FakeGarminGateway(), now=NOW)

    assert isinstance(result, SyncStarted)
    refreshed_orphan = session.get(SyncRun, orphan.id)
    assert refreshed_orphan is not None
    assert refreshed_orphan.status == "abandoned"
