"""Integration tests for `app.api.readiness_mapping` — the seam that maps
stored `daily_metrics` rows (via `app.store.repositories`) into the
engine-owned, I/O-free `MetricsSnapshot` (`app.readiness.types`).

Per PR4's documented deviation, this mapping did not exist before Phase 6:
the engine intentionally never imports `app.store`, so something else has
to translate repository output into `MetricsSnapshot` before
`compute_readiness` can be called against real stored data. Real Postgres
via `testcontainers`, since the rolling-baseline queries this mapping
depends on only work against Postgres (SQLite unit tests cover table
structure only, see `tests/unit/test_models.py`).
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api.readiness_mapping import build_snapshot
from app.readiness.types import MetricsSnapshot
from app.readiness.weights import DEFAULT_WEIGHTS
from app.store.models import Base
from app.store.repositories import upsert_daily_metrics


@pytest.fixture()
def session(postgres_container: str) -> Iterator[Session]:
    engine = create_engine(postgres_container)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    Base.metadata.drop_all(engine)
    engine.dispose()


def test_cold_start_with_no_rows_yields_empty_unavailable_snapshot(
    session: Session,
) -> None:
    as_of = dt.date(2026, 3, 1)

    snapshot = build_snapshot(session, as_of=as_of)

    assert isinstance(snapshot, MetricsSnapshot)
    assert snapshot.as_of == as_of
    assert snapshot.usable_days == 0
    assert set(snapshot.factors) == set(DEFAULT_WEIGHTS.factor_weights)
    for observation in snapshot.factors.values():
        assert observation.value is None
        assert observation.baseline is None


def test_today_value_present_but_baseline_insufficient_below_sixty_days(
    session: Session,
) -> None:
    """Fewer than 60 days of history: today's value is still surfaced, but
    `baseline` must stay `None` rather than a partial mean — the mapping
    must not silently reinterpret health-metrics-store's "insufficient
    history" sentinel as a usable baseline."""
    as_of = dt.date(2026, 3, 1)
    for offset in range(10):
        day = as_of - dt.timedelta(days=offset)
        upsert_daily_metrics(session, metric_date=day, hrv_last_night=50 + offset)
    session.commit()

    snapshot = build_snapshot(session, as_of=as_of)

    hrv = snapshot.factors["hrv"]
    assert hrv.value == 50.0
    assert hrv.baseline is None
    assert snapshot.usable_days == 10


def test_sixty_days_of_history_produces_a_usable_baseline(session: Session) -> None:
    """The baseline window is the trailing 60 days BEFORE `as_of` (not
    including today's own row) — a deliberate mapping-layer interpretation
    so a factor's personal baseline never includes the very reading it is
    being compared against, and so baseline availability never depends on
    whether *today's* value happens to be present (see the "missing
    today's value" test below)."""
    as_of = dt.date(2026, 3, 1)
    for offset in range(61):  # today (offset 0) + 60 prior days
        day = as_of - dt.timedelta(days=offset)
        upsert_daily_metrics(
            session,
            metric_date=day,
            hrv_last_night=50,
            sleep_score=70,
            resting_hr=55,
            stress_avg=30,
            body_battery_max=80,
            acute_load=100,
        )
    session.commit()

    snapshot = build_snapshot(session, as_of=as_of)

    assert snapshot.usable_days == 61
    for factor in DEFAULT_WEIGHTS.factor_weights:
        observation = snapshot.factors[factor]
        assert observation.value is not None
        assert observation.baseline is not None
        assert observation.baseline.n == 60
        assert observation.baseline.mean == pytest.approx(observation.value)
        assert observation.baseline.stddev == pytest.approx(0.0)


def test_missing_todays_value_still_reports_a_baseline_when_covered(
    session: Session,
) -> None:
    """Degraded mode (readiness-scoring's "Degraded Mode for Missing
    Factors"): a factor can have a full 60-day baseline but be missing
    *today's* reading specifically — only possible because the baseline
    window deliberately excludes `as_of` itself (see the test above)."""
    as_of = dt.date(2026, 3, 1)
    for offset in range(1, 61):
        day = as_of - dt.timedelta(days=offset)
        upsert_daily_metrics(session, metric_date=day, hrv_last_night=50)
    # today itself has a row (so usable_days counts it) but no hrv reading
    upsert_daily_metrics(session, metric_date=as_of, sleep_score=70)
    session.commit()

    snapshot = build_snapshot(session, as_of=as_of)

    hrv = snapshot.factors["hrv"]
    assert hrv.value is None
    assert hrv.baseline is not None
    assert hrv.baseline.n == 60
