"""RED-first test for the shared fixture loader (task 2.4 REFACTOR)."""

from __future__ import annotations

import datetime as dt

from app.garmin.fake import FakeGarminGateway
from app.garmin.port import ENDPOINTS, SLEEP
from tests.fixtures.garmin_loader import load_garmin_fixtures


def test_load_garmin_fixtures_returns_a_map_keyed_by_endpoint_then_date() -> None:
    fixtures = load_garmin_fixtures()
    for endpoint in ENDPOINTS:
        assert endpoint in fixtures
        by_date = fixtures[endpoint]
        assert by_date, f"expected at least one recorded date for {endpoint}"
        for key in by_date:
            assert isinstance(key, dt.date)


def test_loaded_fixtures_wire_directly_into_fake_gateway() -> None:
    fixtures = load_garmin_fixtures()
    fake = FakeGarminGateway(fixtures=fixtures)
    recorded_dates = sorted(fixtures[SLEEP].keys())
    first_day = recorded_dates[0]
    assert fake.fetch_sleep(first_day) == fixtures[SLEEP][first_day]
