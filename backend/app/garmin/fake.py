"""`FakeGarminGateway` — the test double that satisfies `GarminGateway`.

SYNTHETIC DATA NOTICE
======================
Every payload this module returns is **synthetically generated**, shaped to
match the real `garminconnect==0.3.8` typed response models
(`garminconnect.typed.HrvData`, `SleepData`, `BodyBatteryEntry`,
`TrainingReadiness` — inspected directly from the installed library, not
guessed from documentation) plus best-effort shapes for `get_stress_data`
and `get_training_status`, which that library version does not ship typed
models for.

This is a deliberate placeholder: the user has not yet supplied real Garmin
Connect credentials, so no real login/fetch has ever been recorded in this
project. **Follow-up (tracked in apply-progress, not a blocker): once real
credentials are available, run `GarminConnectGateway` once against the live
API, capture the actual response shapes into `tests/fixtures/garmin/*.json`,
and replace or validate these synthetic payloads against them.**

`FakeGarminGateway` is used in every pytest run in this repo (see
`app/garmin/port.py` docstring) so CI never touches live Garmin and never
risks the documented 429 account-lockout behavior from repeated login
attempts.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from app.garmin.errors import GarminAuthError, GarminNetworkError, GarminRateLimitError
from app.garmin.port import (
    ACTIVITIES,
    BODY_BATTERY,
    HRV,
    SLEEP,
    STRESS,
    TRAINING_STATUS,
)

FixtureMap = dict[str, dict[dt.date, Any]]


class FakeGarminGateway:
    """Replays synthetic (or injected, e.g. loaded-from-JSON) fixtures.

    Args:
        fixtures: optional pre-built `{endpoint: {date: payload}}` map, e.g.
            from `tests/fixtures/garmin_loader.load_garmin_fixtures()`. When
            a (endpoint, date) pair is missing, falls back to the built-in
            deterministic synthetic generator so any date "just works" —
            useful for Phase 3/4 baseline tests that need many days of
            plausible history.
        auth_error: when True, `login()` raises `GarminAuthError` (simulates
            401/403/MFA — for exercising the 0-retry circuit breaker).
        rate_limited: when True, `login()` raises `GarminRateLimitError`
            (simulates 429).
        network_error: when True, `login()` raises `GarminNetworkError`
            (simulates a network failure / 5xx).
    """

    def __init__(
        self,
        fixtures: FixtureMap | None = None,
        *,
        auth_error: bool = False,
        rate_limited: bool = False,
        network_error: bool = False,
    ) -> None:
        self._fixtures: FixtureMap = fixtures or {}
        self._auth_error = auth_error
        self._rate_limited = rate_limited
        self._network_error = network_error
        self._logged_in = False
        self.login_call_count = 0

    def login(self) -> None:
        self.login_call_count += 1
        if self._auth_error:
            raise GarminAuthError("simulated 401 Unauthorized (fake gateway)")
        if self._rate_limited:
            raise GarminRateLimitError("simulated 429 Too Many Requests (fake gateway)")
        if self._network_error:
            raise GarminNetworkError("simulated network failure (fake gateway)")
        self._logged_in = True

    def fetch_sleep(self, metric_date: dt.date) -> dict[str, Any]:
        return self._lookup(SLEEP, metric_date, _synthetic_sleep)

    def fetch_hrv(self, metric_date: dt.date) -> dict[str, Any]:
        return self._lookup(HRV, metric_date, _synthetic_hrv)

    def fetch_stress(self, metric_date: dt.date) -> dict[str, Any]:
        return self._lookup(STRESS, metric_date, _synthetic_stress)

    def fetch_body_battery(self, metric_date: dt.date) -> list[dict[str, Any]]:
        return self._lookup(BODY_BATTERY, metric_date, _synthetic_body_battery)

    def fetch_training_status(self, metric_date: dt.date) -> dict[str, Any]:
        return self._lookup(TRAINING_STATUS, metric_date, _synthetic_training_status)

    def fetch_activities(self, metric_date: dt.date) -> list[dict[str, Any]]:
        return self._lookup(ACTIVITIES, metric_date, _synthetic_activities)

    def _lookup(self, endpoint: str, metric_date: dt.date, synth: Any) -> Any:
        by_date = self._fixtures.get(endpoint, {})
        if metric_date in by_date:
            return by_date[metric_date]
        return synth(metric_date)


def _seed(metric_date: dt.date) -> int:
    """Small deterministic PRNG seed derived from the date so different
    dates yield slightly different (but reproducible) synthetic values —
    useful once Phase 3/4 tests need varied multi-day history."""
    return metric_date.toordinal()


def _synthetic_sleep(metric_date: dt.date) -> dict[str, Any]:
    seed = _seed(metric_date)
    total_seconds = 6 * 3600 + (seed % 5) * 600  # ~6h-6h50m
    deep = int(total_seconds * 0.18)
    light = int(total_seconds * 0.55)
    rem = int(total_seconds * 0.20)
    awake = total_seconds - deep - light - rem
    overall_score = 65 + (seed % 25)  # 65-89
    date_str = metric_date.isoformat()
    return {
        "dailySleepDTO": {
            "userProfilePK": 1,
            "calendarDate": date_str,
            "sleepTimeSeconds": total_seconds,
            "napTimeSeconds": 0,
            "sleepWindowConfirmed": True,
            "deepSleepSeconds": deep,
            "lightSleepSeconds": light,
            "remSleepSeconds": rem,
            "awakeSleepSeconds": max(awake, 0),
            "sleepStartTimestampGMT": f"{date_str}T05:30:00.0",
            "sleepEndTimestampGMT": f"{date_str}T12:15:00.0",
            "sleepStartTimestampLocal": f"{date_str}T22:30:00.0",
            "sleepEndTimestampLocal": f"{date_str}T05:15:00.0",
            "avgSleepHRV": 45 + (seed % 15),
            "avgSpO2": 96.0,
            "avgRespirationValue": 14.5,
            "lowestRespirationValue": 12.0,
            "highestRespirationValue": 17.0,
            "sleepScores": {
                "overall": {"value": overall_score, "qualifierKey": "GOOD"},
                "totalDuration": {"value": 80, "qualifierKey": "GOOD"},
                "stress": {"value": 75, "qualifierKey": "GOOD"},
                "awakeCount": {"value": 90, "qualifierKey": "EXCELLENT"},
                "remPercentage": {"value": 70, "qualifierKey": "GOOD"},
                "restlessness": {"value": 78, "qualifierKey": "GOOD"},
            },
        }
    }


def _synthetic_hrv(metric_date: dt.date) -> dict[str, Any]:
    seed = _seed(metric_date)
    last_night_avg = 42 + (seed % 20)  # 42-61 ms
    date_str = metric_date.isoformat()
    return {
        "userProfilePK": 1,
        "hrvSummary": {
            "calendarDate": date_str,
            "weeklyAvg": 48.0,
            "lastNightAvg": float(last_night_avg),
            "lastNight5MinHigh": float(last_night_avg + 12),
            "status": "BALANCED",
            "feedbackPhrase": "HRV_BALANCED_7",
            "baseline": {
                "lowUpper": 30.0,
                "balancedLow": 35.0,
                "balancedUpper": 60.0,
                "markerValue": 0.5,
            },
        },
        "hrvReadings": [],
        "startTimestampGMT": f"{date_str}T05:30:00.0",
        "endTimestampGMT": f"{date_str}T12:15:00.0",
        "startTimestampLocal": f"{date_str}T22:30:00.0",
        "endTimestampLocal": f"{date_str}T05:15:00.0",
        "sleepStartTimestampGMT": f"{date_str}T05:30:00.0",
        "sleepEndTimestampGMT": f"{date_str}T12:15:00.0",
    }


def _synthetic_stress(metric_date: dt.date) -> dict[str, Any]:
    # NOTE: garminconnect==0.3.8 ships no typed model for get_stress_data /
    # get_all_day_stress; this shape is a best-effort placeholder based on
    # the general Garmin Connect wellness-endpoint pattern and MUST be
    # cross-checked against a real recorded payload once credentials exist.
    seed = _seed(metric_date)
    avg = 20 + (seed % 30)
    date_str = metric_date.isoformat()
    return {
        "userProfilePK": 1,
        "calendarDate": date_str,
        "avgStressLevel": avg,
        "maxStressLevel": min(avg + 40, 100),
        "stressChartValueOffset": 1,
        "stressChartYAxisOrigin": -1,
        "stressValueDescriptorsDTOList": [],
        "stressValuesArray": [],
    }


def _synthetic_body_battery(metric_date: dt.date) -> list[dict[str, Any]]:
    seed = _seed(metric_date)
    charged = 60 + (seed % 30)
    drained = 50 + (seed % 25)
    date_str = metric_date.isoformat()
    return [
        {
            "date": date_str,
            "charged": charged,
            "drained": drained,
            "startTimestampGMT": f"{date_str}T05:00:00.0",
            "endTimestampGMT": f"{date_str}T23:59:00.0",
            "startTimestampLocal": f"{date_str}T22:00:00.0",
            "endTimestampLocal": f"{date_str}T16:59:00.0",
            "bodyBatteryValuesArray": [
                [f"{date_str}T05:00:00.0", 55 + (seed % 20)],
                [f"{date_str}T12:00:00.0", 30 + (seed % 15)],
                [f"{date_str}T20:00:00.0", 65 + (seed % 10)],
            ],
        }
    ]


def _synthetic_training_status(metric_date: dt.date) -> dict[str, Any]:
    # NOTE: garminconnect==0.3.8 ships no typed model for get_training_status;
    # this shape approximates the well-known `mostRecentTrainingLoadBalance` /
    # `acuteTrainingLoadDTO` nesting from the live API and MUST be
    # cross-checked against a real recorded payload once credentials exist.
    seed = _seed(metric_date)
    acute = 250 + (seed % 200)
    chronic = 300 + (seed % 100)
    date_str = metric_date.isoformat()
    return {
        "userProfilePK": 1,
        "mostRecentTrainingStatus": {
            "latestTrainingStatusData": {
                "1": {
                    "calendarDate": date_str,
                    "trainingStatus": 4,
                    "trainingStatusFeedbackPhrase": "PRODUCTIVE",
                    "acuteTrainingLoadDTO": {
                        "dailyTrainingLoadAcute": acute,
                        "dailyTrainingLoadChronic": chronic,
                        "dailyAcuteChronicWorkloadRatio": round(acute / chronic, 2),
                        "minTrainingLoadChronic": chronic - 40,
                        "maxTrainingLoadChronic": chronic + 40,
                    },
                }
            }
        },
    }


def _synthetic_activities(metric_date: dt.date) -> list[dict[str, Any]]:
    seed = _seed(metric_date)
    if seed % 3 == 0:
        return []  # rest day — no activities, a realistic and important case
    date_str = metric_date.isoformat()
    return [
        {
            "activityId": 10_000_000 + seed,
            "activityName": "Morning Run",
            "startTimeLocal": f"{date_str}T06:30:00",
            "startTimeGMT": f"{date_str}T13:30:00",
            "activityType": {"typeKey": "running", "typeId": 1},
            "distance": 5000.0 + (seed % 10) * 100,
            "duration": 1800.0 + (seed % 10) * 20,
            "averageHR": 140 + (seed % 20),
            "maxHR": 165 + (seed % 15),
            "calories": 420 + (seed % 50),
        }
    ]
