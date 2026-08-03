"""Adapter error-mapping + 0-retry-on-auth-failure contract (task 2.3).

Exercises `GarminConnectGateway` with a dependency-injected fake client
object (NOT `FakeGarminGateway` — a raw stand-in for `garminconnect.Garmin`
itself) so this validates the adapter's own exception-mapping logic without
touching the network or importing the real gateway port's fake.
"""

from __future__ import annotations

import datetime as dt

import pytest
from garminconnect import (
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)

from app.garmin.adapter import GarminConnectGateway
from app.garmin.errors import GarminAuthError, GarminNetworkError, GarminRateLimitError


class _RaisingClient:
    """Stands in for `garminconnect.Garmin`; raises whatever the test wants
    from `login()` so the adapter's mapping/retry logic is exercised without
    a real network call."""

    def __init__(self, login_side_effect: Exception | tuple[str | None, str | None]):
        self._login_side_effect = login_side_effect
        self.login_call_count = 0

    def login(self, tokenstore: str | None = None) -> tuple[str | None, str | None]:
        self.login_call_count += 1
        if isinstance(self._login_side_effect, Exception):
            raise self._login_side_effect
        return self._login_side_effect


def _adapter(client: _RaisingClient) -> GarminConnectGateway:
    return GarminConnectGateway(
        email="user@example.com",
        password="pw",
        token_cache_path="C:/tmp/token-cache",
        client=client,
    )


def test_authentication_error_maps_to_typed_auth_error_with_zero_retries() -> None:
    client = _RaisingClient(GarminConnectAuthenticationError("401 unauthorized"))
    gateway = _adapter(client)
    with pytest.raises(GarminAuthError):
        gateway.login()
    # 0-retry policy (design.md): the adapter itself must not retry a failed
    # login internally — exactly one attempt.
    assert client.login_call_count == 1


def test_too_many_requests_error_maps_to_typed_rate_limit_error() -> None:
    client = _RaisingClient(GarminConnectTooManyRequestsError("429"))
    gateway = _adapter(client)
    with pytest.raises(GarminRateLimitError):
        gateway.login()
    assert client.login_call_count == 1


def test_connection_error_maps_to_typed_network_error() -> None:
    client = _RaisingClient(GarminConnectConnectionError("connection reset"))
    gateway = _adapter(client)
    with pytest.raises(GarminNetworkError):
        gateway.login()
    assert client.login_call_count == 1


def test_mfa_required_response_maps_to_typed_auth_error() -> None:
    # garminconnect.Garmin.login() returns (mfa_status, token) where
    # mfa_status is non-None when MFA is required — this backend is
    # unattended and cannot complete an interactive MFA challenge.
    client = _RaisingClient(("NEEDS_MFA", None))
    gateway = _adapter(client)
    with pytest.raises(GarminAuthError, match="MFA"):
        gateway.login()


def test_clean_login_does_not_raise() -> None:
    client = _RaisingClient((None, None))
    gateway = _adapter(client)
    gateway.login()  # must not raise
    assert client.login_call_count == 1


def test_fetch_lazily_logs_in_exactly_once() -> None:
    client = _RaisingClient((None, None))
    client.get_sleep_data = lambda cdate: {"dailySleepDTO": {"calendarDate": cdate}}
    gateway = _adapter(client)
    assert client.login_call_count == 0  # constructing the gateway must not log in
    gateway.fetch_sleep(dt.date(2026, 1, 1))
    assert client.login_call_count == 1
    gateway.fetch_sleep(dt.date(2026, 1, 2))
    assert client.login_call_count == 1  # second fetch reuses the session


def test_fetch_hrv_returns_empty_dict_when_client_returns_none() -> None:
    client = _RaisingClient((None, None))
    client.get_hrv_data = lambda cdate: None
    gateway = _adapter(client)
    assert gateway.fetch_hrv(dt.date(2026, 1, 1)) == {}


def test_unmapped_library_exception_maps_to_typed_network_error() -> None:
    # Reproduces a real incident: garth (the auth library garminconnect
    # wraps) exhausted its own internal login-backend fallbacks (mobile+cffi,
    # mobile+requests) after repeated 429s and raised an exception type that
    # garminconnect itself never re-raises as one of its three documented
    # error classes. Previously this escaped `_call()` unmapped, crashed the
    # ASGI app mid-request, and left the sync_runs row stuck at "running"
    # forever since `execute_and_release`'s except clauses never fired.
    class _UnmappedLibraryError(Exception):
        """Stands in for e.g. garth.exc.GarthHTTPError — anything the
        garminconnect package doesn't itself wrap."""

    client = _RaisingClient(_UnmappedLibraryError("mobile+requests returned 429"))
    gateway = _adapter(client)
    with pytest.raises(GarminNetworkError):
        gateway.login()
    assert client.login_call_count == 1
