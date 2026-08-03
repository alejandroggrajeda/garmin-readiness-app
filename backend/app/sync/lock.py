"""Postgres advisory-lock mutex guarding manual sync (design.md, "Advisory
lock retained as a duplicate-sync mutex" — accidental double-taps and
concurrent syncs from multiple devices/tabs, not scheduler contention since
there is no scheduler).

`pg_try_advisory_lock` / `pg_advisory_unlock` are SESSION-scoped: the lock
lives on the exact physical connection that acquired it, and releases
automatically if that connection drops (design.md's "Self-healing
property" — a spun-down Render instance frees the lock for free). This is
also why the connection MUST be the Neon *direct* endpoint, never
`-pooler` — PgBouncer transaction pooling can hand a "session"'s next
statement to a different physical backend, silently breaking this session
affinity (see `app/store/session.py` and `tests/integration/test_lock.py`
for the full regression note).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.sql import func

#: Arbitrary fixed application key for the one global sync mutex this app
#: has. A single-user app needs exactly one lock, so no per-resource
#: derivation is needed.
SYNC_LOCK_KEY: int = 0x_5A17C5A9  # "SALTCS" left as a mnemonic, no semantic meaning


def try_acquire_lock(session: Session, key: int = SYNC_LOCK_KEY) -> bool:
    """Non-blocking acquire. Returns `True` if the lock was free and is now
    held by `session`'s connection, `False` if another connection holds
    it."""
    return bool(session.execute(select(func.pg_try_advisory_lock(key))).scalar())


def release_lock(session: Session, key: int = SYNC_LOCK_KEY) -> None:
    """Releases the lock if `session`'s connection holds it. A no-op (per
    Postgres semantics) if it doesn't — safe to call unconditionally in a
    `finally` block."""
    session.execute(select(func.pg_advisory_unlock(key)))
