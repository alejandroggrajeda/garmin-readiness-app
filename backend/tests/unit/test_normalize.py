"""Unit tests for `app.sync.normalize` — pure functions, no DB/Docker.

`raw_to_daily_metrics_fields` is tested against the exact synthetic shapes
`app/garmin/fake.py` generates (mirrors the real `garminconnect==0.3.8`
typed models per its own docstring), so this doubles as a regression check
that the mapping keeps working if `fake.py`'s generator ever changes.
"""

from __future__ import annotations

import datetime as dt

from app.garmin.fake import (
    _synthetic_body_battery,
    _synthetic_hrv,
    _synthetic_sleep,
    _synthetic_stress,
    _synthetic_training_status,
)
from app.sync.normalize import compute_backfill_dates, raw_to_daily_metrics_fields


def _raw_bundle(day: dt.date) -> dict[str, object]:
    return {
        "sleep": _synthetic_sleep(day),
        "hrv": _synthetic_hrv(day),
        "stress": _synthetic_stress(day),
        "body_battery": _synthetic_body_battery(day),
        "training_status": _synthetic_training_status(day),
        "activities": [],
    }


def test_raw_to_daily_metrics_fields_maps_sleep_and_hrv() -> None:
    day = dt.date(2026, 3, 1)
    raw = _raw_bundle(day)

    fields = raw_to_daily_metrics_fields(raw)

    dto = raw["sleep"]["dailySleepDTO"]
    assert fields["sleep_duration_s"] == dto["sleepTimeSeconds"]
    assert fields["sleep_score"] == dto["sleepScores"]["overall"]["value"]
    summary = raw["hrv"]["hrvSummary"]
    assert fields["hrv_last_night"] == round(summary["lastNightAvg"])
    assert fields["hrv_status"] == summary["status"]


def test_raw_to_daily_metrics_fields_maps_stress_body_battery_and_load() -> None:
    day = dt.date(2026, 3, 2)
    raw = _raw_bundle(day)

    fields = raw_to_daily_metrics_fields(raw)

    assert fields["stress_avg"] == raw["stress"]["avgStressLevel"]
    bb_values = [v[1] for v in raw["body_battery"][0]["bodyBatteryValuesArray"]]
    assert fields["body_battery_max"] == max(bb_values)
    assert fields["body_battery_min"] == min(bb_values)
    load = raw["training_status"]["mostRecentTrainingStatus"][
        "latestTrainingStatusData"
    ]["1"]["acuteTrainingLoadDTO"]
    assert fields["acute_load"] == load["dailyTrainingLoadAcute"]
    assert fields["chronic_load"] == load["dailyTrainingLoadChronic"]


def test_raw_to_daily_metrics_fields_tolerates_missing_endpoints() -> None:
    """Degraded mode (readiness-scoring, Phase 4): a raw bundle missing an
    endpoint entirely must not raise — that factor is simply absent from
    the returned fields dict."""
    fields = raw_to_daily_metrics_fields({"sleep": None, "hrv": {}})

    assert "sleep_duration_s" not in fields
    assert "hrv_last_night" not in fields


def test_compute_backfill_dates_first_run_returns_max_days_ending_today() -> None:
    today = dt.date(2026, 3, 15)

    dates = compute_backfill_dates(set(), today, max_days=14)

    assert len(dates) == 14
    assert dates[-1] == today
    assert dates == sorted(dates)  # oldest-first
    assert dates[0] == today - dt.timedelta(days=13)


def test_compute_backfill_dates_always_includes_today_even_if_already_synced() -> None:
    today = dt.date(2026, 3, 15)
    existing = {today}

    dates = compute_backfill_dates(existing, today, max_days=14)

    assert today in dates


def test_compute_backfill_dates_extends_backward_from_earliest_existing_day() -> None:
    """Backfill progress needs no dedicated column — the next batch is
    derived as the missing days before `min(daily_metrics.metric_date)`
    (design.md, "Migration / Rollout")."""
    today = dt.date(2026, 3, 15)
    existing = {today - dt.timedelta(days=i) for i in range(5)}  # 5 recent days

    dates = compute_backfill_dates(existing, today, max_days=14)

    earliest_existing = today - dt.timedelta(days=4)
    assert min(dates) < earliest_existing
    assert len(dates) == 14
    assert all(d not in existing or d == today for d in dates)


def test_compute_backfill_dates_is_resumable_across_runs() -> None:
    """Feeding the previous run's written dates back in as `existing`
    continues strictly further back — never re-covering the same ground
    (other than always re-touching `today`)."""
    today = dt.date(2026, 3, 15)
    run_one = compute_backfill_dates(set(), today, max_days=14)

    existing_after_run_one = set(run_one)
    run_two = compute_backfill_dates(existing_after_run_one, today, max_days=14)

    overlap = (set(run_two) & existing_after_run_one) - {today}
    assert overlap == set()
    assert min(run_two) < min(run_one)
