"""Shared pytest fixtures.

`postgres_container` is session-scoped and lazily started only by tests
that request it (Phase 3+ store/repository tests). Tests that don't depend
on it — like the Phase 1 health-check test — never touch Docker.
"""

from collections.abc import Iterator

import pytest


@pytest.fixture(scope="session")
def postgres_container() -> Iterator[str]:
    """Yields a live Postgres connection URL backed by a disposable
    testcontainer. Requires a local Docker daemon; only imported/started
    when a test explicitly depends on this fixture.

    `testcontainers` defaults to the `psycopg2` driver in the URL it
    returns; the app (and this test suite) standardizes on `psycopg`
    (psycopg3, see `app/store/session.py`), so the driver segment is
    swapped before yielding.
    """
    from testcontainers.postgres import PostgresContainer

    with PostgresContainer("postgres:16-alpine", driver="psycopg") as container:
        yield container.get_connection_url()
