"""SQLAlchemy models for the append-only health metrics store.

Two tables per design.md ("Data Model"):

- `raw_payloads`: append-only. Every synced Garmin response is INSERTed,
  never UPDATEd or DELETEd, so normalization and scoring stay re-runnable
  from full history (design.md, "Technical Approach"). There is no unique
  constraint on `(metric_date, endpoint)` — a re-sync of a day appends
  another row instead of overwriting the previous one, satisfying
  health-metrics-store's "Append-Only Daily Persistence" requirement at
  the table this raw ingestion layer owns.
- `daily_metrics`: the derived, upserted per-day cache the readiness
  engine reads. `metric_date` is the primary key; the repository layer's
  Postgres `ON CONFLICT (metric_date) DO UPDATE` (see
  `app/store/repositories.py`) makes re-syncing a day idempotent per
  design.md's advisory-lock decision, while `raw_payloads` still preserves
  every original observation for that day.

`payload` uses the generic `JSON` type with a `postgresql` variant of
`JSONB` so `tests/unit/test_models.py` can exercise table structure
against an in-memory SQLite engine without Docker, while production
(and `tests/integration/test_repositories.py`, via testcontainers) get
real Postgres JSONB.
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import DateTime, ForeignKey, JSON, LargeBinary, Numeric, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

_PayloadType = JSON().with_variant(JSONB(), "postgresql")


class Base(DeclarativeBase):
    pass


class RawPayload(Base):
    """Append-only raw Garmin response, keyed by an opaque id (never by
    date), so multiple syncs of the same day never collide."""

    __tablename__ = "raw_payloads"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    metric_date: Mapped[dt.date] = mapped_column(nullable=False, index=True)
    endpoint: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    payload: Mapped[dict] = mapped_column(_PayloadType, nullable=False)
    fetched_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class DailyMetric(Base):
    """Derived, upserted per-day metrics cache. One row per `metric_date`.

    `source_run_id` references `sync_runs.id` (Phase 5). The FK constraint
    was deferred until this migration since `sync_runs` did not exist when
    `daily_metrics` was first created (Phase 3).
    """

    __tablename__ = "daily_metrics"

    metric_date: Mapped[dt.date] = mapped_column(primary_key=True)
    hrv_last_night: Mapped[int | None] = mapped_column(nullable=True)
    hrv_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    body_battery_max: Mapped[int | None] = mapped_column(nullable=True)
    body_battery_min: Mapped[int | None] = mapped_column(nullable=True)
    sleep_score: Mapped[int | None] = mapped_column(nullable=True)
    sleep_duration_s: Mapped[int | None] = mapped_column(nullable=True)
    stress_avg: Mapped[int | None] = mapped_column(nullable=True)
    resting_hr: Mapped[int | None] = mapped_column(nullable=True)
    recovery_time_h: Mapped[float | None] = mapped_column(
        Numeric(5, 2), nullable=True
    )
    acute_load: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)
    chronic_load: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)
    synced_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    source_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sync_runs.id"), nullable=True
    )


class SyncRun(Base):
    """One row per manual sync attempt (garmin-sync's Manual Sync
    requirement). `id` doubles as the `run_id` surfaced to the client on
    `202`/`409` and polled via `GET /api/sync/runs/{id}`.

    `heartbeat_at` lets `app/sync/reaper.py` detect a run whose process was
    killed mid-sync (e.g. Render spin-down) and mark it `abandoned` instead
    of leaving it stuck `running` forever, which would otherwise strand the
    advisory lock's bookkeeping (the lock itself self-releases when the
    connection drops — see design.md's "Self-healing property" — but the
    row still needs reaping so `GET .../runs/{id}` doesn't lie).
    """

    __tablename__ = "sync_runs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="running")
    started_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    heartbeat_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error: Mapped[str | None] = mapped_column(String(1024), nullable=True)


class GarminSession(Base):
    """Singleton row (`id=1`) holding the cached Garmin session and the
    auth-failure / rate-limit circuit breaker flags (design.md's "Auth
    failures fail loudly, never retry-loop").

    `token_cache_enc` is schema-ready for the Fernet-encrypted
    `python-garminconnect` token cache; wiring the adapter to actually
    read/write it (instead of its current filesystem `token_cache_path`)
    is deferred past this PR — see apply-progress Deviations.
    """

    __tablename__ = "garmin_session"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    token_cache_enc: Mapped[bytes | None] = mapped_column(
        LargeBinary, nullable=True
    )
    auth_locked: Mapped[bool] = mapped_column(nullable=False, default=False)
    cooldown_until: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
