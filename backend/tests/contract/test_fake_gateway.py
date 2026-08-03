"""Behavioral contract for `FakeGarminGateway` (task 2.2).

Covers: determinism (repeatable payloads), per-date variation (useful for
later baseline/history tests), the three typed error simulations, and that
injected fixtures (from `tests/fixtures/garmin_loader`) take priority over
the built-in synthetic generator.
"""

from __future__ import annotations

import datetime as dt

import pytest

from app.garmin.errors import GarminAuthError, GarminNetworkError, GarminRateLimitError
from app.garmin.fake import FakeGarminGateway
from app.garmin.port import SLEEP


def test_login_succeeds_by_default_and_counts_calls() -> None:
    fake = FakeGarminGateway()
    assert fake.login_call_count == 0
    fake.login()
    assert fake.login_call_count == 1


def test_login_raises_typed_auth_error_when_simulated() -> None:
    fake = FakeGarminGateway(auth_error=True)
    with pytest.raises(GarminAuthError):
        fake.login()


def test_login_raises_typed_rate_limit_error_when_simulated() -> None:
    fake = FakeGarminGateway(rate_limited=True)
    with pytest.raises(GarminRateLimitError):
        fake.login()


def test_login_raises_typed_network_error_when_simulated() -> None:
    fake = FakeGarminGateway(network_error=True)
    with pytest.raises(GarminNetworkError):
        fake.login()


def test_fetch_sleep_is_deterministic_for_the_same_date() -> None:
    fake = FakeGarminGateway()
    day = dt.date(2026, 2, 1)
    first = fake.fetch_sleep(day)
    second = fake.fetch_sleep(day)
    assert first == second


def test_fetch_sleep_varies_across_different_dates() -> None:
    fake = FakeGarminGateway()
    a = fake.fetch_sleep(dt.date(2026, 2, 1))
    b = fake.fetch_sleep(dt.date(2026, 2, 2))
    assert a != b


def test_fetch_activities_includes_realistic_rest_days() -> None:
    fake = FakeGarminGateway()
    # Sweep a window and confirm at least one day comes back empty (rest
    # day) and at least one comes back non-empty (activity day) — both are
    # realistic and both must be handled downstream (Phase 5 normalize).
    days = [dt.date(2026, 2, 1) + dt.timedelta(days=i) for i in range(9)]
    results = [fake.fetch_activities(d) for d in days]
    assert any(r == [] for r in results)
    assert any(r != [] for r in results)


def test_injected_fixture_overrides_synthetic_generator() -> None:
    day = dt.date(2026, 3, 3)
    recorded_payload = {"dailySleepDTO": {"calendarDate": "2026-03-03", "sleepTimeSeconds": 1}}
    fake = FakeGarminGateway(fixtures={SLEEP: {day: recorded_payload}})
    assert fake.fetch_sleep(day) == recorded_payload
    # A date not present in the injected fixture still falls back to the
    # synthetic generator rather than raising.
    other_day = dt.date(2026, 3, 4)
    assert fake.fetch_sleep(other_day) != recorded_payload
    assert isinstance(fake.fetch_sleep(other_day), dict)
