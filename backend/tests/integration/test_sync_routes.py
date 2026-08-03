"""Integration tests for `POST /api/sync`, `GET /api/sync/runs/{id}`, and
`POST /api/sync/unlock` — wiring only (business logic depth is covered by
`tests/integration/test_sync_service.py`); real Postgres via
`testcontainers`, `FakeGarminGateway` injected via dependency override.

`readiness-api`'s "Manual Sync Endpoint" requirement: trigger while idle
starts a sync and returns its outcome.
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
from app.garmin.fake import FakeGarminGateway
from app.main import app
from app.store.models import Base, GarminSession, SyncRun


@pytest.fixture()
def client(postgres_container: str) -> Iterator[TestClient]:
    engine = create_engine(postgres_container)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def _override_sessionmaker() -> sessionmaker[Session]:
        return session_factory

    def _override_gateway() -> FakeGarminGateway:
        return FakeGarminGateway()

    def _override_get_db() -> Iterator[Session]:
        db_session = session_factory()
        try:
            yield db_session
        finally:
            db_session.close()

    app.dependency_overrides[deps.get_sync_sessionmaker] = _override_sessionmaker
    app.dependency_overrides[deps.get_db] = _override_get_db
    app.dependency_overrides[deps.get_garmin_gateway] = _override_gateway

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    engine.dispose()


def test_trigger_sync_while_idle_returns_202_with_a_run_id(client: TestClient) -> None:
    response = client.post("/api/sync")

    assert response.status_code == 202
    body = response.json()
    assert "run_id" in body
    uuid.UUID(body["run_id"])  # valid UUID string


def test_trigger_sync_while_already_running_returns_409(
    client: TestClient, postgres_container: str
) -> None:
    """`TestClient` runs `BackgroundTasks` to completion before `.post()`
    returns (they execute inside the same ASGI call the test blocks on),
    so a genuinely in-flight run can't be observed by firing two real
    requests back-to-back here. Simulate it directly: hold the advisory
    lock on a connection kept open for the whole test (its own engine, so
    the app's connection pool can never silently recycle it back to us —
    the same physical-connection-affinity concern the pooled-vs-direct
    regression note in `tests/integration/test_lock.py` documents) and
    insert a `running` row via a separate, normally-committed session."""
    from app.sync.lock import release_lock, try_acquire_lock

    holder_engine = create_engine(postgres_container)
    holder_conn = holder_engine.connect()
    assert try_acquire_lock(holder_conn) is True
    with Session(holder_engine) as commit_session:
        in_flight = SyncRun(status="running")
        commit_session.add(in_flight)
        commit_session.commit()
        in_flight_id = in_flight.id

    response = client.post("/api/sync")

    assert response.status_code == 409
    assert response.json()["run_id"] == str(in_flight_id)

    release_lock(holder_conn)
    holder_conn.close()
    holder_engine.dispose()


def test_polling_the_run_id_returns_its_status(client: TestClient) -> None:
    started = client.post("/api/sync")
    run_id = started.json()["run_id"]

    response = client.get(f"/api/sync/runs/{run_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == run_id
    assert body["status"] in {"running", "completed"}


def test_polling_an_unknown_run_id_returns_404(client: TestClient) -> None:
    response = client.get(f"/api/sync/runs/{uuid.uuid4()}")

    assert response.status_code == 404


def test_unlock_clears_the_auth_locked_breaker(client: TestClient) -> None:
    engine = client.app.dependency_overrides[deps.get_sync_sessionmaker]()()
    engine.add(GarminSession(id=1, auth_locked=True))
    engine.commit()
    engine.close()

    response = client.post("/api/sync/unlock")

    assert response.status_code == 200
    check = client.app.dependency_overrides[deps.get_sync_sessionmaker]()()
    breaker = check.get(GarminSession, 1)
    assert breaker is not None
    assert breaker.auth_locked is False
    check.close()


def test_no_garmin_credential_or_session_token_ever_appears_in_a_response(
    client: TestClient,
) -> None:
    """Credential Security requirement (garmin-sync spec)."""
    started = client.post("/api/sync")
    run_id = started.json()["run_id"]
    polled = client.get(f"/api/sync/runs/{run_id}")

    for response in (started, polled):
        body_text = response.text.lower()
        assert "password" not in body_text
        assert "token" not in body_text
