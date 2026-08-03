"""`GET /api/readiness/today`, `GET /api/readiness/history` — readiness-api's
"Today's Readiness Endpoint" and "History Endpoint" requirements.

No `readiness_scores` cache table exists in this schema (see apply-progress
Phase 5 deviation #4 — the simplified `sync_runs` shape; a scores cache was
never added either). Both routes compute on demand via
`app.api.readiness_mapping.build_snapshot` + `compute_readiness` — cheap at
this app's single-user, small-history scale, and keeps `readiness_scores`
naturally re-derivable instead of a second source of truth to keep in sync.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api import deps
from app.api.readiness_mapping import build_snapshot
from app.readiness.engine import compute_readiness
from app.readiness.types import ReadinessResult
from app.readiness.weights import DEFAULT_WEIGHTS
from app.store.models import SyncRun
from app.store.repositories import get_latest_metric_date

router = APIRouter(
    prefix="/api/readiness", tags=["readiness"], dependencies=[Depends(deps.require_api_key)]
)


def _serialize_result(
    result: ReadinessResult,
    *,
    as_of: dt.date,
    data_stale: bool,
    last_synced_at: dt.datetime | None,
) -> dict[str, Any]:
    return {
        "state": result.state,
        "score": result.score,
        "band": result.band,
        "factors": [
            {
                "name": f.name,
                "available": f.available,
                "z_value": f.z_value,
                "weight": f.weight,
                "points": f.points,
            }
            for f in result.factors
        ],
        "dominant_factor": result.dominant_factor,
        "reason": result.reason,
        "confidence": result.confidence,
        "weights_version": result.weights_version,
        "days_until_scored": result.days_until_scored,
        "as_of": as_of.isoformat(),
        "data_stale": data_stale,
        "last_synced_at": last_synced_at.isoformat() if last_synced_at else None,
    }


def _last_synced_at(session: Session) -> dt.datetime | None:
    stmt = (
        select(SyncRun.completed_at)
        .where(SyncRun.status == "completed")
        .order_by(SyncRun.completed_at.desc())
        .limit(1)
    )
    return session.scalar(stmt)


@router.get("/today")
def get_today(session: Session = Depends(deps.get_db)) -> dict[str, Any]:
    today = dt.datetime.now(dt.timezone.utc).date()
    latest_date = get_latest_metric_date(session, on_or_before=today)

    as_of = latest_date if latest_date is not None else today
    data_stale = latest_date is not None and latest_date != today

    snapshot = build_snapshot(session, as_of=as_of)
    result = compute_readiness(snapshot, DEFAULT_WEIGHTS)

    return _serialize_result(
        result,
        as_of=as_of,
        data_stale=data_stale,
        last_synced_at=_last_synced_at(session),
    )


@router.get("/history")
def get_history(
    days: int = 30, session: Session = Depends(deps.get_db)
) -> list[dict[str, Any]]:
    today = dt.datetime.now(dt.timezone.utc).date()
    entries: list[dict[str, Any]] = []
    for offset in range(days - 1, -1, -1):
        day = today - dt.timedelta(days=offset)
        snapshot = build_snapshot(session, as_of=day)
        result = compute_readiness(snapshot, DEFAULT_WEIGHTS)
        entries.append(
            {
                "date": day.isoformat(),
                "score": result.score,
                "band": result.band,
                "state": result.state,
            }
        )
    return entries
