"""Integration tests for `app.sync.lock` — the Postgres advisory-lock mutex
that guards accidental double-tap/multi-device manual syncs (design.md,
"Advisory lock retained as a duplicate-sync mutex").

Real ephemeral Postgres via `testcontainers` (the `postgres_container`
fixture, `tests/conftest.py`) — SQLite has no `pg_try_advisory_lock`.

**Neon pooled-vs-direct regression note**: `pg_try_advisory_lock` is
SESSION-scoped (tied to the physical backend connection), which is exactly
what PgBouncer's *transaction* pooling mode silently breaks — a pooled
connection can hand the same logical session's next statement to a
DIFFERENT physical backend, making the "lock" apply to a connection nobody
is holding onto, so a second request can slip through undetected
(design.md, "Database — Neon free tier", load-bearing gotcha). This is why
`app/store/session.py` requires the Neon *direct* endpoint in production.
`testcontainers` gives every test its own unpooled Postgres instance, so a
literal pooled-vs-direct comparison isn't reproducible here; instead,
`test_lock_is_scoped_to_the_acquiring_connection_not_shared_globally`
below proves the property PgBouncer's transaction pooling would violate:
the lock lives on ONE connection and a genuinely different connection
cannot see it as released until that first connection releases it — this
is the exact session affinity a pooler in transaction mode does not
guarantee.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.store.models import Base
from app.sync.lock import SYNC_LOCK_KEY, release_lock, try_acquire_lock


@pytest.fixture()
def engine(postgres_container: str) -> Iterator[object]:
    eng = create_engine(postgres_container)
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)
    eng.dispose()


def test_lock_free_is_acquired_successfully(engine: object) -> None:
    with Session(engine) as session:
        assert try_acquire_lock(session) is True
        release_lock(session)


def test_double_tap_second_acquire_on_a_different_connection_fails(
    engine: object,
) -> None:
    """The "Manual sync already in flight" scenario (garmin-sync spec): a
    second, concurrent attempt must NOT also acquire the lock."""
    with Session(engine) as first, Session(engine) as second:
        assert try_acquire_lock(first) is True
        assert try_acquire_lock(second) is False
        release_lock(first)


def test_lock_is_released_and_becomes_acquirable_again(engine: object) -> None:
    with Session(engine) as first:
        assert try_acquire_lock(first) is True
        release_lock(first)

    with Session(engine) as second:
        assert try_acquire_lock(second) is True
        release_lock(second)


def test_lock_is_scoped_to_the_acquiring_connection_not_shared_globally(
    engine: object,
) -> None:
    """Regression guard for the PgBouncer transaction-pooling trap
    (design.md): the lock must stay tied to the exact connection that
    acquired it. A different connection must be unable to release a lock
    it never held (asserted indirectly: releasing on `second` while `first`
    still holds it does not free it for a third connection)."""
    with Session(engine) as first, Session(engine) as second, Session(
        engine
    ) as third:
        assert try_acquire_lock(first) is True

        release_lock(second)  # no-op: `second` never held SYNC_LOCK_KEY

        assert try_acquire_lock(third) is False  # still held by `first`
        release_lock(first)
        assert try_acquire_lock(third) is True
        release_lock(third)


def test_sync_lock_key_is_a_stable_module_constant() -> None:
    assert isinstance(SYNC_LOCK_KEY, int)
