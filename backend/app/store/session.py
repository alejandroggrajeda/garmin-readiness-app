"""Database engine/session wiring.

Uses the Neon *direct* (non-pooled) endpoint — never the `-pooler` host —
because `pg_try_advisory_lock` is session-scoped and silently breaks under
PgBouncer transaction pooling (see design.md, "Database — Neon free tier").

Both Render (compute) and Neon (Postgres) suspend when idle, so a stale
socket from a previously-suspended compute must be recycled rather than
raising on the first query after a wake. `pool_pre_ping` handles that; the
short `pool_recycle` prevents SQLAlchemy from reusing a connection the
server may have already dropped.
"""

from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings

# Neon computes suspend after ~5 minutes of inactivity; recycle well before
# any plausible platform-side idle-connection cutoff.
POOL_RECYCLE_SECONDS = 280


@lru_cache
def get_engine() -> Engine:
    settings = get_settings()
    return create_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_recycle=POOL_RECYCLE_SECONDS,
    )


@lru_cache
def get_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), autoflush=False, autocommit=False)


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding a request-scoped session."""
    session = get_sessionmaker()()
    try:
        yield session
    finally:
        session.close()
