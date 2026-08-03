"""Static `X-API-Key` guard (design.md: "Single-user: no accounts, one
static `X-API-Key`."). Applied at router level to every route that reads
or triggers a write of personal data — sync and readiness — per
`tasks.md` task 6.3. `GET /healthz` stays unauthenticated by design (the
mobile client's warm-up ping, see design.md's "Cold start" decision).
"""

from __future__ import annotations

from fastapi import Header, HTTPException, status

from app.config import get_settings


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """FastAPI dependency: raises `401` unless `X-API-Key` matches the
    configured single-user key. Compared against `get_settings()` (not a
    cached constant) so tests and deployments can vary `API_KEY` via env
    without restarting the process's import graph."""
    settings = get_settings()
    if not x_api_key or x_api_key != settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing or invalid X-API-Key",
        )
