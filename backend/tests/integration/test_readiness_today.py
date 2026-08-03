"""Integration tests for `GET /api/readiness/today` (readiness-api's
"Today's Readiness Endpoint" requirement) — real Postgres via
`testcontainers`, `X-API-Key` guard exercised for real (no dependency
override), since authorization is this route's own concern.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.api import deps
from app.config import get_settings
from app.main import app
from app.store.models import Base, SyncRun
from app.store.repositories import upsert_daily_metrics

API_KEY = get_settings().api_key


@pytest.fixture()
def client(postgres_container: str) -> Iterator[TestClient]:
    engine = create_engine(postgres_container)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def _override_get_db() -> Iterator[Session]:
        db_session = session_factory()
        try:
            yield db_session
        finally:
            db_session.close()

    app.dependency_overrides[deps.get_db] = _override_get_db

    with TestClient(app, headers={"X-API-Key": API_KEY}) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture()
def db(client: TestClient) -> Iterator[Session]:
    override = app.dependency_overrides[deps.get_db]
    gen = override()
    session = next(gen)
    try:
        yield session
    finally:
        session.close()


def test_no_data_at_all_returns_calibrating(client: TestClient) -> None:
    response = client.get("/api/readiness/today")

    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "calibrating"
    assert body["score"] is None
    assert body["last_synced_at"] is None
    assert body["data_stale"] is False


def test_sixty_days_including_today_returns_a_scored_result(
    client: TestClient, db: Session
) -> None:
    """Baseline days (offsets 1-60) carry small day-to-day variation so
    their stddev is nonzero — a perfectly flat history produces a
    degenerate (zero-stddev) baseline, which the engine correctly treats
    as "no meaningful deviation possible" and excludes from scoring
    (`app.readiness.baselines.raw_z_score`)."""
    today = dt.date.today()
    upsert_daily_metrics(
        db,
        metric_date=today,
        hrv_last_night=60,
        sleep_score=70,
        resting_hr=50,
        stress_avg=25,
        body_battery_max=80,
        acute_load=100,
    )
    for offset in range(1, 61):
        day = today - dt.timedelta(days=offset)
        wiggle = offset % 3
        upsert_daily_metrics(
            db,
            metric_date=day,
            hrv_last_night=58 + wiggle,
            sleep_score=68 + wiggle,
            resting_hr=48 + wiggle,
            stress_avg=23 + wiggle,
            body_battery_max=78 + wiggle,
            acute_load=98 + wiggle,
        )
    db.commit()

    response = client.get("/api/readiness/today")

    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "scored"
    assert isinstance(body["score"], int)
    assert body["as_of"] == today.isoformat()
    assert body["data_stale"] is False


def test_todays_data_missing_falls_back_to_last_synced_day_marked_stale(
    client: TestClient, db: Session
) -> None:
    today = dt.date.today()
    stale_day = today - dt.timedelta(days=3)
    for offset in range(60):
        day = stale_day - dt.timedelta(days=offset)
        upsert_daily_metrics(db, metric_date=day, hrv_last_night=55)
    db.commit()

    response = client.get("/api/readiness/today")

    assert response.status_code == 200
    body = response.json()
    assert body["as_of"] == stale_day.isoformat()
    assert body["data_stale"] is True


def test_last_synced_at_reflects_the_most_recent_completed_sync_run(
    client: TestClient, db: Session
) -> None:
    older = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
    newer = dt.datetime(2026, 2, 1, tzinfo=dt.timezone.utc)
    db.add(SyncRun(id=uuid.uuid4(), status="completed", started_at=older, completed_at=older))
    db.add(SyncRun(id=uuid.uuid4(), status="completed", started_at=newer, completed_at=newer))
    # a still-running or failed run must never be picked as "last synced"
    db.add(SyncRun(id=uuid.uuid4(), status="running", started_at=newer))
    db.commit()

    response = client.get("/api/readiness/today")

    assert response.status_code == 200
    assert response.json()["last_synced_at"] == newer.isoformat()


def test_missing_api_key_is_rejected(client: TestClient) -> None:
    response = client.get("/api/readiness/today", headers={"X-API-Key": ""})

    assert response.status_code in (401, 403)


def test_wrong_api_key_is_rejected(client: TestClient) -> None:
    response = client.get("/api/readiness/today", headers={"X-API-Key": "not-the-real-key"})

    assert response.status_code in (401, 403)
