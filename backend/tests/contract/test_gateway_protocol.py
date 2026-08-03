"""Contract test: both the real adapter and the fake satisfy the same
`GarminGateway` Protocol (design.md — "GarminGateway port isolates the
unofficial library"). This is the test that guarantees `app/sync/service.py`
(Phase 5) can depend on the Protocol alone and swap implementations freely.
"""

from __future__ import annotations

import datetime as dt

from app.garmin.adapter import GarminConnectGateway
from app.garmin.fake import FakeGarminGateway
from app.garmin.port import ENDPOINTS, GarminGateway


def test_fake_gateway_satisfies_protocol() -> None:
    fake = FakeGarminGateway()
    assert isinstance(fake, GarminGateway)


def test_adapter_satisfies_protocol_without_logging_in() -> None:
    # Constructing the adapter must never touch the network — no client.login()
    # call happens until fetch/login is explicitly invoked.
    adapter = GarminConnectGateway(
        email="user@example.com",
        password="not-a-real-password",
        token_cache_path="C:/tmp/does-not-matter",
    )
    assert isinstance(adapter, GarminGateway)


def test_both_implementations_expose_every_declared_endpoint_method() -> None:
    fake = FakeGarminGateway()
    adapter = GarminConnectGateway(
        email="user@example.com",
        password="not-a-real-password",
        token_cache_path="C:/tmp/does-not-matter",
    )
    for endpoint in ENDPOINTS:
        method_name = f"fetch_{endpoint}"
        assert callable(getattr(fake, method_name)), method_name
        assert callable(getattr(adapter, method_name)), method_name


def test_fake_fetch_methods_accept_a_date_and_return_data(
) -> None:
    fake = FakeGarminGateway()
    today = dt.date(2026, 1, 15)
    fake.login()
    assert isinstance(fake.fetch_sleep(today), dict)
    assert isinstance(fake.fetch_hrv(today), dict)
    assert isinstance(fake.fetch_stress(today), dict)
    assert isinstance(fake.fetch_body_battery(today), list)
    assert isinstance(fake.fetch_training_status(today), dict)
    assert isinstance(fake.fetch_activities(today), list)
