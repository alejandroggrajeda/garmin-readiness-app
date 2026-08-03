"""Manual sync orchestration (garmin-sync's "Manual Sync" requirement).

Split into two functions so the request/response boundary and the actual
sync work stay separately testable:

- `begin_sync`: reaper, auth-lock/cooldown breaker check, advisory-lock
  acquire, `sync_runs` row creation. Fast; returns quickly.
- `execute_and_release`: the fetch/normalize/write loop for the run
  `begin_sync` created, heartbeating between days. ALWAYS releases the
  advisory lock and closes `session` in its `finally`, whether the run
  succeeded, failed non-fatally, or hit the auth/rate-limit breaker
  (garmin-sync's "Sync Failure Is Non-Fatal" requirement — this function
  never raises for a Garmin-side failure).

`routes/sync.py` wires these together: `begin_sync` runs inline in the
request handler (fast enough to answer synchronously), then
`execute_and_release` is handed to `BackgroundTasks` so `POST /api/sync`
can return `202` immediately while the client polls
`GET /api/sync/runs/{id}` — which, per design.md, is also what keeps a
free-tier Render instance awake for the run's duration.
"""

from __future__ import annotations

import datetime as dt
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.garmin.errors import GarminAuthError, GarminNetworkError, GarminRateLimitError
from app.garmin.port import GarminGateway
from app.store import repositories
from app.store.models import GarminSession, SyncRun
from app.sync.lock import release_lock, try_acquire_lock
from app.sync.normalize import compute_backfill_dates, raw_to_daily_metrics_fields
from app.sync.reaper import reap_abandoned_runs

#: design.md, "Migration / Rollout": bounded chunk per run so any single
#: sync finishes inside the client's poll window.
MAX_DAYS_PER_RUN = 14
#: design.md's auth-failure/circuit-breaker table.
COOLDOWN_HOURS = 6
MAX_NETWORK_RETRIES = 2
_GARMIN_SESSION_ID = 1


@dataclass(frozen=True)
class SyncStarted:
    run_id: uuid.UUID


@dataclass(frozen=True)
class SyncAlreadyRunning:
    run_id: uuid.UUID | None
    started_at: dt.datetime


@dataclass(frozen=True)
class SyncAuthLocked:
    """Circuit breaker engaged — needs `POST /api/sync/unlock`."""


@dataclass(frozen=True)
class SyncCooldown:
    retry_after_seconds: int


TriggerResult = SyncStarted | SyncAlreadyRunning | SyncAuthLocked | SyncCooldown


def begin_sync(
    session: Session, *, gateway: GarminGateway, now: dt.datetime | None = None
) -> TriggerResult:
    """`POST /api/sync`'s synchronous half. Never runs the actual fetch —
    see module docstring."""
    now = now or dt.datetime.now(dt.timezone.utc)
    reap_abandoned_runs(session, now=now)
    session.commit()

    breaker = _get_or_create_garmin_session(session)
    if breaker.auth_locked:
        return SyncAuthLocked()
    if breaker.cooldown_until is not None and breaker.cooldown_until > now:
        remaining = int((breaker.cooldown_until - now).total_seconds())
        return SyncCooldown(retry_after_seconds=max(0, remaining))

    if not try_acquire_lock(session):
        in_flight = session.scalars(
            select(SyncRun).where(SyncRun.status == "running").order_by(
                SyncRun.started_at.desc()
            )
        ).first()
        session.rollback()
        if in_flight is not None:
            return SyncAlreadyRunning(run_id=in_flight.id, started_at=in_flight.started_at)
        return SyncAlreadyRunning(run_id=None, started_at=now)

    run = SyncRun(status="running", started_at=now, heartbeat_at=now)
    session.add(run)
    session.commit()
    return SyncStarted(run_id=run.id)


def execute_and_release(
    session: Session,
    run_id: uuid.UUID,
    *,
    gateway: GarminGateway,
    now: dt.datetime | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """The sync work for the run `begin_sync` created on `session` (which
    holds the advisory lock). Never raises — every Garmin-side failure is
    caught, recorded on the run, and surfaces as stored state instead
    (garmin-sync's "Sync Failure Is Non-Fatal" requirement)."""
    now = now or dt.datetime.now(dt.timezone.utc)
    try:
        run = session.get(SyncRun, run_id)
        if run is None:  # pragma: no cover - defensive, should not happen
            return
        try:
            _login_with_retry(gateway, sleep=sleep)
            _sync_days(session, run, gateway=gateway, now=now)
            run.status = "completed"
            run.completed_at = now
            session.commit()
        except GarminAuthError as exc:
            session.rollback()
            run = session.get(SyncRun, run_id)
            run.status = "failed"
            run.error = f"auth: {exc}"
            run.completed_at = now
            breaker = _get_or_create_garmin_session(session)
            breaker.auth_locked = True
            session.commit()
        except GarminRateLimitError as exc:
            session.rollback()
            run = session.get(SyncRun, run_id)
            run.status = "failed"
            run.error = f"rate_limited: {exc}"
            run.completed_at = now
            breaker = _get_or_create_garmin_session(session)
            breaker.cooldown_until = now + dt.timedelta(hours=COOLDOWN_HOURS)
            session.commit()
        except GarminNetworkError as exc:
            session.rollback()
            run = session.get(SyncRun, run_id)
            run.status = "abandoned"
            run.error = f"network: {exc}"
            run.completed_at = now
            session.commit()
    finally:
        release_lock(session)
        session.close()


def _sync_days(
    session: Session, run: SyncRun, *, gateway: GarminGateway, now: dt.datetime | None
) -> None:
    today = (now or dt.datetime.now(dt.timezone.utc)).date()
    existing_dates = {
        m.metric_date
        for m in repositories.get_daily_metrics_range(
            session, start_date=dt.date(1970, 1, 1), end_date=today
        )
    }
    dates = compute_backfill_dates(existing_dates, today, max_days=MAX_DAYS_PER_RUN)

    for metric_date in dates:
        raw = {
            "sleep": gateway.fetch_sleep(metric_date),
            "hrv": gateway.fetch_hrv(metric_date),
            "stress": gateway.fetch_stress(metric_date),
            "body_battery": gateway.fetch_body_battery(metric_date),
            "training_status": gateway.fetch_training_status(metric_date),
            "activities": gateway.fetch_activities(metric_date),
        }
        for endpoint, payload in raw.items():
            repositories.insert_raw_payload(
                session, metric_date=metric_date, endpoint=endpoint, payload=payload
            )
        fields = raw_to_daily_metrics_fields(raw)
        repositories.upsert_daily_metrics(
            session, metric_date=metric_date, source_run_id=run.id, **fields
        )
        run.heartbeat_at = dt.datetime.now(dt.timezone.utc)
        session.commit()


def _login_with_retry(
    gateway: GarminGateway,
    *,
    max_retries: int = MAX_NETWORK_RETRIES,
    sleep: Callable[[float], None],
) -> None:
    """design.md: "Network / 5xx | Max 2 retries, exponential backoff, then
    abandon the run". Auth/rate-limit errors are never retried — they
    propagate on the first attempt."""
    attempt = 0
    while True:
        try:
            gateway.login()
            return
        except GarminNetworkError:
            if attempt >= max_retries:
                raise
            sleep(2**attempt)
            attempt += 1


def _get_or_create_garmin_session(session: Session) -> GarminSession:
    breaker = session.get(GarminSession, _GARMIN_SESSION_ID)
    if breaker is None:
        breaker = GarminSession(id=_GARMIN_SESSION_ID)
        session.add(breaker)
        session.flush()
    return breaker
