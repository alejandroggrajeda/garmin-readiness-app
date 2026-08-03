"""`GarminConnectGateway` — the real `GarminGateway` adapter.

This is the ONLY module in this codebase allowed to `import garminconnect`
(https://github.com/cyberjunky/python-garminconnect, PyPI package
`garminconnect`, pinned to `0.3.8` — see `pyproject.toml`). Every method
name and exception type referenced below was confirmed against the
installed `garminconnect==0.3.8` package (`Garmin.login`, `get_sleep_data`,
`get_hrv_data`, `get_stress_data`, `get_body_battery`, `get_training_status`,
`get_activities_by_date`, and the `GarminConnect*Error` hierarchy), not
guessed from documentation.

KNOWN LIMITATION — untested against the live API in this session: the user
has not yet provided real Garmin credentials, so `login()`/`fetch_*` here
have never executed against garmin.com. The unit-testable surface (error
mapping, 0-retry-on-auth-failure behavior, MFA handling) IS covered via
dependency-injected fake `client` objects (see `tests/contract/
test_adapter_login.py`). **Follow-up, not a blocker**: once credentials
exist, run this adapter once against the live API to confirm the real
response shapes, then replace the synthetic fixtures in `fake.py` /
`tests/fixtures/garmin/` with real recorded ones.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any, Protocol

from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)

from app.garmin.errors import GarminAuthError, GarminNetworkError, GarminRateLimitError


class _GarminClient(Protocol):
    """The subset of `garminconnect.Garmin`'s surface this adapter uses.
    Exists purely so tests can inject a lightweight fake client instead of
    the real network-backed one."""

    def login(self, tokenstore: str | None = None) -> tuple[str | None, str | None]: ...
    def get_sleep_data(self, cdate: str) -> dict[str, Any]: ...
    def get_hrv_data(self, cdate: str) -> dict[str, Any] | None: ...
    def get_stress_data(self, cdate: str) -> dict[str, Any]: ...
    def get_body_battery(self, startdate: str, enddate: str | None = None) -> list[dict[str, Any]]: ...
    def get_training_status(self, cdate: str) -> dict[str, Any]: ...
    def get_activities_by_date(
        self, startdate: str, enddate: str | None = None, activitytype: str | None = None
    ) -> list[dict[str, Any]]: ...


class GarminConnectGateway:
    """Real `GarminGateway` implementation backed by `python-garminconnect`.

    Args:
        email: Garmin account email (server-side only, per design.md — never
            shipped to the mobile client).
        password: Garmin account password.
        token_cache_path: filesystem path `garminconnect`/`garth` uses to
            persist the session token so a cold Render start reuses the
            session instead of re-logging in (design.md — "more important in
            rev 2, since a sleeping instance restarts often"). Encrypting
            this at rest into `garmin_session.token_cache_enc` is Phase 5
            scope; this constructor only accepts *where* to read/write it.
        client: optional pre-built client satisfying `_GarminClient`. Tests
            inject a fake here to exercise error-mapping and the 0-retry
            auth policy without any network access. Production code leaves
            this `None` and a real `garminconnect.Garmin` is constructed.
    """

    def __init__(
        self,
        email: str,
        password: str,
        token_cache_path: str | Path,
        *,
        client: _GarminClient | None = None,
    ) -> None:
        self._token_cache_path = str(token_cache_path)
        self._client: _GarminClient = client or Garmin(email=email, password=password)
        self._logged_in = False

    def login(self) -> None:
        """Raises `GarminAuthError` / `GarminRateLimitError` /
        `GarminNetworkError`. Never retries — see `app/garmin/errors.py`."""

        def _do_login() -> tuple[str | None, str | None]:
            return self._client.login(self._token_cache_path)

        mfa_status, _legacy_token = self._call(_do_login)
        if mfa_status is not None:
            # This backend is unattended (server-side credentials, no
            # interactive prompt) — an account that unexpectedly requires
            # MFA cannot complete login and must be treated as an auth
            # failure so the 0-retry circuit breaker engages (design.md).
            raise GarminAuthError(
                "Garmin account requires MFA; unattended server login "
                "cannot complete it. Configure an MFA-exempt account or "
                "pre-seed a valid token cache."
            )
        self._logged_in = True

    def fetch_sleep(self, metric_date: dt.date) -> dict[str, Any]:
        self._ensure_logged_in()
        return self._call(lambda: self._client.get_sleep_data(metric_date.isoformat()))

    def fetch_hrv(self, metric_date: dt.date) -> dict[str, Any]:
        self._ensure_logged_in()
        result = self._call(lambda: self._client.get_hrv_data(metric_date.isoformat()))
        return result or {}

    def fetch_stress(self, metric_date: dt.date) -> dict[str, Any]:
        self._ensure_logged_in()
        return self._call(lambda: self._client.get_stress_data(metric_date.isoformat()))

    def fetch_body_battery(self, metric_date: dt.date) -> list[dict[str, Any]]:
        self._ensure_logged_in()
        date_str = metric_date.isoformat()
        return self._call(lambda: self._client.get_body_battery(date_str, date_str))

    def fetch_training_status(self, metric_date: dt.date) -> dict[str, Any]:
        self._ensure_logged_in()
        return self._call(lambda: self._client.get_training_status(metric_date.isoformat()))

    def fetch_activities(self, metric_date: dt.date) -> list[dict[str, Any]]:
        self._ensure_logged_in()
        date_str = metric_date.isoformat()
        return self._call(lambda: self._client.get_activities_by_date(date_str, date_str))

    def _ensure_logged_in(self) -> None:
        if not self._logged_in:
            self.login()

    @staticmethod
    def _call(fn: Any) -> Any:
        """Runs `fn()` and maps the real library's exceptions onto this
        codebase's typed `GarminGatewayError` hierarchy. Centralized here so
        every fetch_* method (and login) shares one mapping policy.

        The catch-all below exists because `garminconnect`'s three
        documented error classes don't cover everything: `garth` (the auth
        library `garminconnect` wraps) can exhaust its own internal
        login-backend fallbacks and raise its own exception type, which
        `garminconnect` never re-wraps. Left unmapped, that escaped `_call()`
        entirely in production, crashed the ASGI request mid-flight, and
        left the `sync_runs` row stuck at "running" forever since
        `execute_and_release`'s typed except clauses never fired. Anything
        unrecognized is treated as a network-layer failure — the safest
        default, since it still engages the same non-retry/non-fatal path
        as a confirmed connection error rather than crashing the request.
        """
        try:
            return fn()
        except GarminConnectAuthenticationError as exc:
            raise GarminAuthError(str(exc)) from exc
        except GarminConnectTooManyRequestsError as exc:
            raise GarminRateLimitError(str(exc)) from exc
        except GarminConnectConnectionError as exc:
            raise GarminNetworkError(str(exc)) from exc
        except Exception as exc:
            raise GarminNetworkError(str(exc)) from exc
