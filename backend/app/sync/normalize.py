"""Pure raw-payload -> `daily_metrics` field mapping, and the chunked
backfill date-selection function.

Both functions are zero-I/O by design (no session, no gateway) so they are
unit-testable without Docker/Postgres, per design.md's Testing Strategy
("Backfill batch derivation ... Pure function over stored date ranges").
"""

from __future__ import annotations

import datetime as dt
from typing import Any

#: `resting_hr` and `recovery_time_h` are in `daily_metrics`'s schema
#: (design.md Data Model) but `GarminGateway` (Phase 2) has no dedicated
#: fetch method for either — the Protocol was widened to six per-endpoint
#: methods that don't include a resting-HR or recovery-time source. Left
#: unmapped here; both columns stay NULL until a future gateway endpoint is
#: added. Flagged in apply-progress Deviations, not silently dropped.
UNMAPPED_FIELDS: tuple[str, ...] = ("resting_hr", "recovery_time_h")


def raw_to_daily_metrics_fields(raw: dict[str, Any]) -> dict[str, object]:
    """Maps one day's raw Garmin payload bundle (`{endpoint: payload}`, the
    same shape `app/sync/service.py` assembles from `GarminGateway.fetch_*`)
    into `daily_metrics` column kwargs for `repositories.upsert_daily_metrics`.

    Missing or malformed endpoints are tolerated — this function never
    raises on absent data (degraded-mode support, readiness-scoring Phase
    4); it simply omits the corresponding field(s).
    """
    fields: dict[str, object] = {}

    sleep = raw.get("sleep") or {}
    dto = sleep.get("dailySleepDTO") or {}
    if dto.get("sleepTimeSeconds") is not None:
        fields["sleep_duration_s"] = dto["sleepTimeSeconds"]
    overall = (dto.get("sleepScores") or {}).get("overall") or {}
    if overall.get("value") is not None:
        fields["sleep_score"] = overall["value"]

    hrv = raw.get("hrv") or {}
    summary = hrv.get("hrvSummary") or {}
    if summary.get("lastNightAvg") is not None:
        fields["hrv_last_night"] = round(summary["lastNightAvg"])
    if summary.get("status") is not None:
        fields["hrv_status"] = summary["status"]

    stress = raw.get("stress") or {}
    if stress.get("avgStressLevel") is not None:
        fields["stress_avg"] = stress["avgStressLevel"]

    body_battery = raw.get("body_battery") or []
    if body_battery:
        entry = body_battery[0] or {}
        values = [
            v[1]
            for v in entry.get("bodyBatteryValuesArray", [])
            if isinstance(v, (list, tuple)) and len(v) == 2
        ]
        if values:
            fields["body_battery_max"] = max(values)
            fields["body_battery_min"] = min(values)

    training_status = raw.get("training_status") or {}
    latest_by_id = (
        training_status.get("mostRecentTrainingStatus") or {}
    ).get("latestTrainingStatusData") or {}
    if latest_by_id:
        first_entry = next(iter(latest_by_id.values()))
        load = first_entry.get("acuteTrainingLoadDTO") or {}
        if load.get("dailyTrainingLoadAcute") is not None:
            fields["acute_load"] = load["dailyTrainingLoadAcute"]
        if load.get("dailyTrainingLoadChronic") is not None:
            fields["chronic_load"] = load["dailyTrainingLoadChronic"]

    return fields


def compute_backfill_dates(
    existing_dates: set[dt.date], today: dt.date, *, max_days: int = 14
) -> list[dt.date]:
    """Selects up to `max_days` dates to fetch this sync run, oldest-first.

    `today` is always included (a re-sync of the current day is cheap and
    idempotent — `upsert_daily_metrics` — and keeps today's numbers fresh
    as the day progresses). The remaining budget walks backward from the
    day before `min(existing_dates)` (or `today` if there is no history
    yet), skipping any date already present, so repeated runs resume
    exactly where the previous one left off without needing a dedicated
    progress column (design.md, "Migration / Rollout").
    """
    needed: list[dt.date] = [today]

    cursor = (min(existing_dates) if existing_dates else today) - dt.timedelta(days=1)
    while len(needed) < max_days:
        if cursor not in existing_dates and cursor not in needed:
            needed.append(cursor)
        cursor -= dt.timedelta(days=1)

    return sorted(needed)
