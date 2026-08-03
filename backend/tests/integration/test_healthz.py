"""GET /healthz — liveness + warm-up probe.

Per design.md ("Interfaces / Contracts"): unauthenticated, no DB access, used
by the mobile client to wake a spun-down Render instance before the user
reaches the sync button.
"""

from fastapi.testclient import TestClient

from app.main import app


def test_healthz_returns_200_ok() -> None:
    client = TestClient(app)

    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_healthz_requires_no_api_key() -> None:
    """Unauthenticated by design — sent before the client has anything to
    authenticate with, while the instance may still be waking up."""
    client = TestClient(app)

    response = client.get("/healthz")  # deliberately no X-API-Key header

    assert response.status_code == 200
