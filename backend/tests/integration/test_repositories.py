"""Integration tests for `app.store.repositories` against a real ephemeral
Postgres (testcontainers) — exercises the Postgres-specific
`ON CONFLICT ... DO UPDATE` upsert path and JSONB payload column that
`tests/unit/test_models.py`'s SQLite fixture cannot cover, plus the
rolling-baseline and usable-days queries health-metrics-store and
readiness-scoring depend on.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.store.models import Base, DailyMetric, RawPayload
from app.store.repositories import (
    Baseline,
    InsufficientHistory,
    count_usable_days,
    get_daily_metrics_range,
    get_rolling_baseline,
    insert_raw_payload,
    upsert_daily_metrics,
)


@pytest.fixture()
def session(postgres_container: str) -> Iterator[Session]:
    engine = create_engine(postgres_container)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    Base.metadata.drop_all(engine)
    engine.dispose()


def test_insert_raw_payload_appends_without_overwriting(session: Session) -> None:
    day = dt.date(2026, 1, 1)
    insert_raw_payload(session, metric_date=day, endpoint="hrv", payload={"v": 1})
    insert_raw_payload(session, metric_date=day, endpoint="hrv", payload={"v": 2})
    session.commit()

    rows = (
        session.query(RawPayload).filter_by(metric_date=day, endpoint="hrv").all()
    )
    assert len(rows) == 2
    assert {row.payload["v"] for row in rows} == {1, 2}


def test_upsert_daily_metrics_inserts_then_updates_in_place(session: Session) -> None:
    day = dt.date(2026, 1, 1)
    upsert_daily_metrics(session, metric_date=day, hrv_last_night=50)
    session.commit()

    upsert_daily_metrics(session, metric_date=day, hrv_last_night=55, resting_hr=48)
    session.commit()

    rows = session.query(DailyMetric).all()
    assert len(rows) == 1
    assert rows[0].hrv_last_night == 55
    assert rows[0].resting_hr == 48


def test_upsert_daily_metrics_rejects_unknown_field(session: Session) -> None:
    with pytest.raises(ValueError):
        upsert_daily_metrics(
            session, metric_date=dt.date(2026, 1, 1), not_a_real_column=1
        )


def test_get_daily_metrics_range_filters_by_date(session: Session) -> None:
    for offset in range(5):
        day = dt.date(2026, 1, 1) + dt.timedelta(days=offset)
        upsert_daily_metrics(session, metric_date=day, hrv_last_night=50 + offset)
    session.commit()

    rows = get_daily_metrics_range(
        session, start_date=dt.date(2026, 1, 2), end_date=dt.date(2026, 1, 3)
    )

    assert [r.metric_date for r in rows] == [
        dt.date(2026, 1, 2),
        dt.date(2026, 1, 3),
    ]


def test_rolling_baseline_insufficient_history_below_window(session: Session) -> None:
    """health-metrics-store: "Insufficient history" scenario — fewer than
    60 days of stored data must return the sentinel, never a partial
    average."""
    as_of = dt.date(2026, 3, 1)
    for offset in range(10):
        day = as_of - dt.timedelta(days=offset)
        upsert_daily_metrics(session, metric_date=day, hrv_last_night=50)
    session.commit()

    result = get_rolling_baseline(
        session, metric="hrv_last_night", window_days=60, as_of=as_of
    )

    assert isinstance(result, InsufficientHistory)
    assert result.available_days == 10
    assert result.window_days == 60


def test_rolling_baseline_returns_mean_when_fully_covered(session: Session) -> None:
    as_of = dt.date(2026, 3, 1)
    values = [40, 41, 42, 43, 44, 45, 46]  # 7 distinct values
    for offset, value in enumerate(values):
        day = as_of - dt.timedelta(days=offset)
        upsert_daily_metrics(session, metric_date=day, hrv_last_night=value)
    session.commit()

    result = get_rolling_baseline(
        session, metric="hrv_last_night", window_days=7, as_of=as_of
    )

    assert isinstance(result, Baseline)
    assert result.n == 7
    assert result.mean == pytest.approx(sum(values) / 7)


def test_rolling_baseline_ignores_null_observations_in_window(session: Session) -> None:
    """A day present in `daily_metrics` but missing this specific factor
    must not count toward coverage — otherwise a partial average could
    leak through."""
    as_of = dt.date(2026, 3, 1)
    for offset in range(7):
        day = as_of - dt.timedelta(days=offset)
        # leave hrv_last_night null on one of the seven days
        value = None if offset == 3 else 50
        upsert_daily_metrics(session, metric_date=day, hrv_last_night=value)
    session.commit()

    result = get_rolling_baseline(
        session, metric="hrv_last_night", window_days=7, as_of=as_of
    )

    assert isinstance(result, InsufficientHistory)
    assert result.available_days == 6


def test_count_usable_days_counts_rows_on_or_before_as_of(session: Session) -> None:
    as_of = dt.date(2026, 3, 1)
    for offset in range(15):
        day = as_of - dt.timedelta(days=offset)
        upsert_daily_metrics(session, metric_date=day, hrv_last_night=50)
    # a day AFTER as_of must not count
    upsert_daily_metrics(
        session, metric_date=as_of + dt.timedelta(days=1), hrv_last_night=50
    )
    session.commit()

    assert count_usable_days(session, as_of=as_of) == 15
