"""The persistence port for synced health metrics.

This is the ONLY module the rest of the backend (readiness engine,
Phase 4; sync service, Phase 5; API routes, Phase 6) should import to read
or write `raw_payloads` and `daily_metrics` — callers never build SQL or
touch `app.store.models` directly, so the append-only-vs-upsert policy and
the "insufficient history" baseline contract stay centralized here.
"""

from __future__ import annotations

import datetime as dt
import statistics
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.store.models import DailyMetric, RawPayload

#: 7/28/60-day windows health-metrics-store's "Rolling Baseline Queries"
#: requirement names explicitly.
BASELINE_WINDOWS: tuple[int, ...] = (7, 28, 60)

_DAILY_METRIC_COLUMNS: set[str] = {
    c.name for c in DailyMetric.__table__.columns if c.name != "metric_date"
}


@dataclass(frozen=True)
class Baseline:
    """A fully-covered rolling baseline for one `daily_metrics` column."""

    metric: str
    window_days: int
    mean: float
    stddev: float
    n: int


@dataclass(frozen=True)
class InsufficientHistory:
    """Returned instead of `Baseline` when the trailing window isn't fully
    covered — health-metrics-store requires this explicit sentinel rather
    than a partial average."""

    metric: str
    window_days: int
    available_days: int


def insert_raw_payload(
    session: Session,
    *,
    metric_date: dt.date,
    endpoint: str,
    payload: dict,
    fetched_at: dt.datetime | None = None,
) -> RawPayload:
    """Always INSERTs a new row. `raw_payloads` is append-only by design —
    there is no update path here, even for a repeated
    `(metric_date, endpoint)` pair (a re-sync of the same day)."""
    row = RawPayload(metric_date=metric_date, endpoint=endpoint, payload=payload)
    if fetched_at is not None:
        row.fetched_at = fetched_at
    session.add(row)
    session.flush()
    return row


def upsert_daily_metrics(
    session: Session, *, metric_date: dt.date, **fields: object
) -> DailyMetric:
    """Insert-or-update the single row for `metric_date` via Postgres
    `ON CONFLICT (metric_date) DO UPDATE`, making a re-sync of the same day
    idempotent per design.md's advisory-lock decision. `raw_payloads`
    still keeps every original observation for that day untouched."""
    unknown = set(fields) - _DAILY_METRIC_COLUMNS
    if unknown:
        raise ValueError(f"Unknown daily_metrics field(s): {sorted(unknown)}")

    stmt = pg_insert(DailyMetric).values(metric_date=metric_date, **fields)
    if fields:
        stmt = stmt.on_conflict_do_update(
            index_elements=[DailyMetric.metric_date],
            set_={key: stmt.excluded[key] for key in fields},
        )
    else:
        stmt = stmt.on_conflict_do_nothing(index_elements=[DailyMetric.metric_date])
    session.execute(stmt)
    session.flush()
    row = session.get(DailyMetric, metric_date)
    assert row is not None  # the upsert above guarantees the row exists
    return row


def get_daily_metrics_range(
    session: Session, *, start_date: dt.date, end_date: dt.date
) -> list[DailyMetric]:
    """Inclusive date-range query used for baseline calculations and
    history views."""
    stmt = (
        select(DailyMetric)
        .where(
            DailyMetric.metric_date >= start_date,
            DailyMetric.metric_date <= end_date,
        )
        .order_by(DailyMetric.metric_date)
    )
    return list(session.scalars(stmt))


def get_rolling_baseline(
    session: Session,
    *,
    metric: str,
    window_days: int,
    as_of: dt.date,
) -> Baseline | InsufficientHistory:
    """7/28/60-day rolling baseline for one `daily_metrics` column.

    Coverage requires `window_days` NON-NULL observations within the
    trailing `[as_of - window_days + 1, as_of]` range — a day that exists
    but is missing this specific factor does not count. Returns
    `InsufficientHistory` rather than a partial average when coverage
    falls short, per health-metrics-store's "Rolling Baseline Queries"
    requirement.
    """
    if metric not in _DAILY_METRIC_COLUMNS:
        raise ValueError(f"Unknown daily_metrics metric: {metric!r}")

    column = getattr(DailyMetric, metric)
    start_date = as_of - dt.timedelta(days=window_days - 1)
    stmt = select(column).where(
        DailyMetric.metric_date >= start_date,
        DailyMetric.metric_date <= as_of,
        column.isnot(None),
    )
    values = [float(v) for v in session.scalars(stmt)]

    if len(values) < window_days:
        return InsufficientHistory(
            metric=metric, window_days=window_days, available_days=len(values)
        )

    return Baseline(
        metric=metric,
        window_days=window_days,
        mean=statistics.fmean(values),
        stddev=statistics.pstdev(values) if len(values) > 1 else 0.0,
        n=len(values),
    )


def get_latest_metric_date(
    session: Session, *, on_or_before: dt.date
) -> dt.date | None:
    """The most recent `daily_metrics.metric_date` on or before
    `on_or_before`, or `None` if no rows exist yet.

    Phase 6 (readiness-api) support: `GET /api/readiness/today`'s stale
    fallback needs to know which day's data to score when today's row is
    missing (e.g. the latest manual sync failed or hasn't happened yet).
    """
    stmt = select(func.max(DailyMetric.metric_date)).where(
        DailyMetric.metric_date <= on_or_before
    )
    return session.scalar(stmt)


def count_usable_days(session: Session, *, as_of: dt.date) -> int:
    """Total number of `daily_metrics` rows on or before `as_of`.

    This is the `usable_days` figure readiness-scoring's calibrating-state
    logic (Phase 4) is computed from: `<14` -> calibrating, `14-59` ->
    `scored` with `confidence = usable_days / 60`, `>=60` -> `confidence
    1.0`. Deliberately uncapped here — the 60-day clamp is the engine's
    responsibility, not the store's.
    """
    stmt = select(func.count()).select_from(DailyMetric).where(
        DailyMetric.metric_date <= as_of
    )
    return session.scalar(stmt) or 0
