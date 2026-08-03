"""Integration tests for `GET /api/readiness/history` (readiness-api's
"History Endpoint" requirement: "one entry per day (score + date)").
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.api import deps
from app.config import get_settings
from app.main import app
from app.store.models import Base
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


def test_thirty_day_history_returns_one_entry_per_day(
    client: TestClient, db: Session
) -> None:
    today = dt.date.today()
    for offset in range(90):
        day = today - dt.timedelta(days=offset)
        upsert_daily_metrics(db, metric_date=day, hrv_last_night=55)
    db.commit()

    response = client.get("/api/readiness/history?days=30")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 30
    dates = [entry["date"] for entry in body]
    assert dates == sorted(dates)
    assert dates[-1] == today.isoformat()
    for entry in body:
        assert set(entry) == {"date", "score", "band", "state"}


def test_history_defaults_to_thirty_days(client: TestClient, db: Session) -> None:
    today = dt.date.today()
    for offset in range(5):
        day = today - dt.timedelta(days=offset)
        upsert_daily_metrics(db, metric_date=day, hrv_last_night=55)
    db.commit()

    response = client.get("/api/readiness/history")

    assert response.status_code == 200
    assert len(response.json()) == 30


def test_history_requires_api_key(client: TestClient) -> None:
    response = client.get("/api/readiness/history", headers={"X-API-Key": ""})

    assert response.status_code in (401, 403)
