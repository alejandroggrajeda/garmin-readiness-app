"""Liveness / warm-up probe. Unauthenticated, no DB access — see
design.md, "Cold start is an expected latency characteristic"."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
