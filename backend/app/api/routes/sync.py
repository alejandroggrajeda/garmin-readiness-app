"""`POST /api/sync`, `GET /api/sync/runs/{id}`, `POST /api/sync/unlock`.

readiness-api's "Manual Sync Endpoint" requirement — the only sync trigger
in this system; no scheduled job ever calls it. Response shapes per
design.md's "Interfaces / Contracts".
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session, sessionmaker

from app.api import deps
from app.garmin.port import GarminGateway
from app.store.models import GarminSession, SyncRun
from app.sync import service

router = APIRouter(
    prefix="/api/sync", tags=["sync"], dependencies=[Depends(deps.require_api_key)]
)


@router.post("", status_code=202)
def trigger_sync(
    background_tasks: BackgroundTasks,
    sync_sessionmaker: sessionmaker[Session] = Depends(deps.get_sync_sessionmaker),
    gateway: GarminGateway = Depends(deps.get_garmin_gateway),
) -> JSONResponse:
    """Opens a DEDICATED session (not `Depends(get_db)`) that stays open —
    holding the advisory lock — across the background task. See
    `app/sync/service.py`'s module docstring."""
    session = sync_sessionmaker()
    try:
        result = service.begin_sync(session, gateway=gateway)
    except Exception:
        session.close()
        raise

    if isinstance(result, service.SyncAlreadyRunning):
        session.close()
        return JSONResponse(
            status_code=409,
            content={
                "run_id": str(result.run_id) if result.run_id else None,
                "started_at": result.started_at.isoformat(),
            },
        )
    if isinstance(result, service.SyncAuthLocked):
        session.close()
        return JSONResponse(status_code=423, content={"auth_locked": True})
    if isinstance(result, service.SyncCooldown):
        session.close()
        return JSONResponse(
            status_code=429,
            content={"retry_after": result.retry_after_seconds},
            headers={"Retry-After": str(result.retry_after_seconds)},
        )

    background_tasks.add_task(
        service.execute_and_release, session, result.run_id, gateway=gateway
    )
    return JSONResponse(status_code=202, content={"run_id": str(result.run_id)})


@router.get("/runs/{run_id}")
def get_run(run_id: uuid.UUID, session: Session = Depends(deps.get_db)) -> dict[str, Any]:
    run = session.get(SyncRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="sync run not found")
    return {
        "id": str(run.id),
        "status": run.status,
        "started_at": run.started_at.isoformat(),
        "heartbeat_at": run.heartbeat_at.isoformat(),
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "error": run.error,
    }


@router.post("/unlock")
def unlock(session: Session = Depends(deps.get_db)) -> dict[str, bool]:
    """API-key-guarded per design.md, via the router-level `require_api_key`
    dependency (`app/api/security.py`, Phase 6 task 6.3)."""
    breaker = session.get(GarminSession, 1)
    if breaker is not None:
        breaker.auth_locked = False
        session.commit()
    return {"auth_locked": False}
