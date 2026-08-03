"""Typed errors raised by any `GarminGateway` implementation.

These map 1:1 to the auth-failure/circuit-breaker table in design.md
("Auth failures fail loudly, never retry-loop"). The rest of the backend
(`app/sync/service.py`, Phase 5) catches these — never the underlying
`garminconnect` library exceptions directly — so the retry/lockout policy
stays centralized regardless of which gateway implementation is injected.
"""

from __future__ import annotations


class GarminGatewayError(Exception):
    """Base class for all typed Garmin gateway errors."""


class GarminAuthError(GarminGatewayError):
    """401 / 403 / MFA-required, or an unattended login that cannot proceed
    without an interactive MFA prompt.

    Caller policy (design.md): **0 retries**. The sync run must be marked
    `failed_auth` and `garmin_session.auth_locked` set to `true`; every
    subsequent sync is rejected with `423` until an explicit manual unlock.
    """


class GarminRateLimitError(GarminGatewayError):
    """429 Too Many Requests.

    Caller policy (design.md): abort immediately, set
    `cooldown_until = now + 6h`. Must NOT be retried within the same run.
    """


class GarminNetworkError(GarminGatewayError):
    """Network failure, timeout, or 5xx from Garmin's servers.

    Caller policy (design.md): retryable — up to 2 retries with exponential
    backoff, then abandon the run (non-fatal; stored data keeps serving).
    """
