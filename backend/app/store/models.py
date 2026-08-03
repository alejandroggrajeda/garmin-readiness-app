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

from sqlalchemy import DateTime, JSON, Numeric, String, func
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

    `source_run_id` forward-references `sync_runs.id` (Phase 5, not yet
    created) as a plain nullable UUID column with no FK constraint — the
    FK is added in the Phase 5 migration once `sync_runs` exists.
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
    source_run_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
