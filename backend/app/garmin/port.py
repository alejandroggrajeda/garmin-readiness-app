"""The `GarminGateway` hexagonal port.

This Protocol is the ONLY thing the rest of the backend (sync service,
normalize, routes, tests) is allowed to depend on for talking to Garmin.
Two implementations exist:

- `app/garmin/adapter.py::GarminConnectGateway` — the real adapter. It is
  the ONLY module in this codebase allowed to `import garminconnect`
  (https://github.com/cyberjunky/python-garminconnect).
- `app/garmin/fake.py::FakeGarminGateway` — replays synthetic/recorded
  fixtures. Used in every CI run and every pytest run in this repo, so
  tests never hit the live Garmin API (avoids burning login attempts that
  trigger Garmin's documented 429 account lockouts).

Each `fetch_*` method returns the raw JSON-shaped payload for exactly one
`raw_payloads.endpoint` value from design.md's data model — normalization
into `daily_metrics` happens later, in `app/sync/normalize.py` (Phase 5),
not here.
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Protocol, runtime_checkable

# Endpoint identifiers stored verbatim in `raw_payloads.endpoint`. Keep this
# tuple in sync with the fetch_* method names below (fetch_{endpoint}).
SLEEP = "sleep"
HRV = "hrv"
STRESS = "stress"
BODY_BATTERY = "body_battery"
TRAINING_STATUS = "training_status"
ACTIVITIES = "activities"

ENDPOINTS: tuple[str, ...] = (
    SLEEP,
    HRV,
    STRESS,
    BODY_BATTERY,
    TRAINING_STATUS,
    ACTIVITIES,
)


@runtime_checkable
class GarminGateway(Protocol):
    """Structural (duck-typed) port. `isinstance(x, GarminGateway)` checks
    method presence, not signatures — the contract test additionally
    verifies every `ENDPOINTS` entry has a matching `fetch_*` method on
    both implementations.
    """

    def login(self) -> None:
        """Authenticate and establish (or resume, via a cached token) a
        session.

        Raises:
            GarminAuthError: on 401 / 403 / MFA-required.
            GarminRateLimitError: on 429.
            GarminNetworkError: on network failure or 5xx.

        Never retries internally — retry/backoff policy belongs to the
        caller (`app/sync/service.py`, Phase 5), not the gateway.
        """
        ...

    def fetch_sleep(self, metric_date: dt.date) -> dict[str, Any]:
        """Raw payload for `raw_payloads.endpoint = "sleep"`."""
        ...

    def fetch_hrv(self, metric_date: dt.date) -> dict[str, Any]:
        """Raw payload for `raw_payloads.endpoint = "hrv"`."""
        ...

    def fetch_stress(self, metric_date: dt.date) -> dict[str, Any]:
        """Raw payload for `raw_payloads.endpoint = "stress"`."""
        ...

    def fetch_body_battery(self, metric_date: dt.date) -> list[dict[str, Any]]:
        """Raw payload for `raw_payloads.endpoint = "body_battery"`."""
        ...

    def fetch_training_status(self, metric_date: dt.date) -> dict[str, Any]:
        """Raw payload for `raw_payloads.endpoint = "training_status"`."""
        ...

    def fetch_activities(self, metric_date: dt.date) -> list[dict[str, Any]]:
        """Raw payload for `raw_payloads.endpoint = "activities"`."""
        ...
