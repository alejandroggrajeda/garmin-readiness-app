"""FastAPI dependency wiring for the sync routes (Phase 5). Deliberately
minimal — `api/security.py` (static `X-API-Key` auth) and the broader
readiness-route DI wiring are Phase 6 scope (tasks.md, task 6.3); these
three dependencies exist now only because `routes/sync.py` needs them.
"""

from __future__ import annotations

from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.garmin.adapter import GarminConnectGateway
from app.garmin.port import GarminGateway
from app.store.session import get_db, get_sessionmaker

__all__ = ["get_db", "get_sync_sessionmaker", "get_garmin_gateway"]


def get_sync_sessionmaker() -> sessionmaker[Session]:
    """A dedicated sessionmaker for `POST /api/sync`'s long-lived session.

    Deliberately NOT `Depends(get_db)`: `pg_try_advisory_lock` is
    session-scoped (see `app/sync/lock.py`), so the same session/connection
    must stay open from acquire through the background task's release —
    FastAPI's per-request session cleanup ordering relative to
    `BackgroundTasks` is not something this route wants to depend on.
    """
    return get_sessionmaker()


def get_garmin_gateway() -> GarminGateway:
    settings = get_settings()
    return GarminConnectGateway(
        settings.garmin_email,
        settings.garmin_password,
        token_cache_path=".garmin_token_cache",
    )
