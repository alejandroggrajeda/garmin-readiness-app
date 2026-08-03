"""Unit tests for the store's SQLAlchemy models — structural properties
only (append-only vs. upsert-eligible), verified against an in-memory
SQLite engine so no Docker/Postgres is required. The Postgres-specific
`ON CONFLICT ... DO UPDATE` upsert path and JSONB payload column are
covered by `tests/integration/test_repositories.py` against a real
testcontainer instead.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.store.models import Base, DailyMetric, RawPayload


@pytest.fixture()
def session() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def test_raw_payloads_appends_a_second_row_for_the_same_date_and_endpoint(
    session: Session,
) -> None:
    """No unique constraint on (metric_date, endpoint) — a re-sync of the
    same day appends another row instead of colliding, per
    health-metrics-store's append-only requirement."""
    day = dt.date(2026, 1, 1)
    session.add(RawPayload(metric_date=day, endpoint="hrv", payload={"v": 1}))
    session.add(RawPayload(metric_date=day, endpoint="hrv", payload={"v": 2}))
    session.commit()

    rows = (
        session.query(RawPayload).filter_by(metric_date=day, endpoint="hrv").all()
    )
    assert len(rows) == 2
    assert {row.payload["v"] for row in rows} == {1, 2}


def test_raw_payloads_rows_are_never_mutated_by_a_later_insert(
    session: Session,
) -> None:
    day = dt.date(2026, 1, 2)
    first = RawPayload(metric_date=day, endpoint="sleep", payload={"score": 70})
    session.add(first)
    session.commit()
    first_id = first.id

    session.add(RawPayload(metric_date=day, endpoint="sleep", payload={"score": 90}))
    session.commit()

    original = session.get(RawPayload, first_id)
    assert original is not None
    assert original.payload == {"score": 70}


def test_daily_metrics_metric_date_is_the_primary_key(session: Session) -> None:
    day = dt.date(2026, 1, 1)
    session.add(DailyMetric(metric_date=day, hrv_last_night=55))
    session.commit()

    session.add(DailyMetric(metric_date=day, hrv_last_night=60))
    with pytest.raises(IntegrityError):
        session.commit()


def test_daily_metrics_allows_partial_missing_factors(session: Session) -> None:
    """Degraded-mode support (readiness-scoring, Phase 4): a day with only
    some metrics populated must still be a valid row."""
    day = dt.date(2026, 1, 3)
    session.add(DailyMetric(metric_date=day, hrv_last_night=55, stress_avg=None))
    session.commit()

    row = session.get(DailyMetric, day)
    assert row is not None
    assert row.hrv_last_night == 55
    assert row.stress_avg is None
