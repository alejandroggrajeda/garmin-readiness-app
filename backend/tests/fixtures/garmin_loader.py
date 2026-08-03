"""Shared loader for the recorded/synthetic Garmin fixture JSON files under
`tests/fixtures/garmin/` (task 2.4 — extracted so every contract/integration
test that needs `FakeGarminGateway(fixtures=...)` shares one loading path
instead of re-implementing JSON-plus-date-parsing per test module).

Deliberately lives in `tests/`, not `app/garmin/` — production code
(`FakeGarminGateway`'s built-in synthetic generator) has no dependency on
the test tree; only tests import this helper.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

from app.garmin.port import ENDPOINTS

FIXTURES_DIR = Path(__file__).parent / "garmin"


def load_garmin_fixtures(
    fixtures_dir: Path | None = None,
) -> dict[str, dict[dt.date, Any]]:
    """Reads every `{endpoint}.json` file in `fixtures_dir` (default:
    `tests/fixtures/garmin/`) and returns `{endpoint: {date: payload}}`,
    ready to hand to `FakeGarminGateway(fixtures=...)`.

    Missing files are skipped (not an error) so a partially-recorded
    fixture set (e.g. only `sleep.json` replaced with real data so far)
    still loads.
    """
    directory = fixtures_dir or FIXTURES_DIR
    result: dict[str, dict[dt.date, Any]] = {}
    for endpoint in ENDPOINTS:
        path = directory / f"{endpoint}.json"
        if not path.exists():
            continue
        raw = json.loads(path.read_text(encoding="utf-8"))
        result[endpoint] = {
            dt.date.fromisoformat(date_str): payload for date_str, payload in raw.items()
        }
    return result
