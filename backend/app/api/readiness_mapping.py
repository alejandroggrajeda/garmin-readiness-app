"""The seam between the DB-aware store and the I/O-free readiness engine.

`app.readiness.*` (Phase 4) intentionally has ZERO imports from
`app.store.*` — see `app/readiness/types.py`'s module docstring — and
`app.store.repositories` (Phase 3) has no reason to know about
`MetricsSnapshot`. Something has to translate `daily_metrics` rows plus
`get_rolling_baseline` results into the engine's plain dataclasses; per
`tasks.md` (task 6.1) that translator is Phase 6's own new module. It is
allowed to import BOTH sides, unlike either one individually.

**Baseline window interpretation (deliberate, not specified verbatim by
design.md)**: a factor's personal baseline is computed over the 60 days
BEFORE `as_of`, never including `as_of` itself. Two reasons: (1) a
baseline should never include the very observation it is being compared
against, and (2) this decouples baseline availability from whether
today's specific reading happens to be present — a day can be fully
"calibrated" (60-day baseline available) while still missing today's
value (readiness-scoring's "Degraded Mode for Missing Factors").
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy.orm import Session

from app.readiness.types import (
    FactorBaseline,
    FactorName,
    FactorObservation,
    MetricsSnapshot,
)
from app.store.repositories import (
    Baseline,
    count_usable_days,
    get_daily_metrics_range,
    get_rolling_baseline,
)

#: `daily_metrics` column each readiness factor is sourced from.
#: `body_battery` uses the daily peak (`body_battery_max`) as the single
#: representative reading — design.md's Data Model stores max/min but the
#: engine (Phase 4) scores one value per factor, and the peak is the more
#: direct proxy for same-day recovery than the trough. `training_load`
#: uses `acute_load` directly (not an acute:chronic ratio): comparing
#: today's acute load to its own 60-day personal baseline via z-score
#: already penalizes deviation in either direction, which is what
#: `training_load`'s `distance_from_target` polarity (weights.py) is for.
FACTOR_COLUMNS: dict[FactorName, str] = {
    "hrv": "hrv_last_night",
    "sleep": "sleep_score",
    "resting_hr": "resting_hr",
    "stress": "stress_avg",
    "body_battery": "body_battery_max",
    "training_load": "acute_load",
}

#: See module docstring — the trailing window used for every factor's
#: personal baseline, matching design.md's `confidence = usable_days / 60`
#: / `full_confidence_at_days` framing (`app/readiness/weights.py`).
BASELINE_WINDOW_DAYS = 60


def build_snapshot(session: Session, *, as_of: dt.date) -> MetricsSnapshot:
    """Builds the `MetricsSnapshot` `compute_readiness` needs for `as_of`,
    reading only through `app.store.repositories` (never raw ORM/SQL here)."""
    today_rows = get_daily_metrics_range(session, start_date=as_of, end_date=as_of)
    today_row = today_rows[0] if today_rows else None

    baseline_as_of = as_of - dt.timedelta(days=1)
    factors: dict[FactorName, FactorObservation] = {}
    for factor, column in FACTOR_COLUMNS.items():
        raw_value = getattr(today_row, column) if today_row is not None else None
        value = float(raw_value) if raw_value is not None else None

        baseline_result = get_rolling_baseline(
            session,
            metric=column,
            window_days=BASELINE_WINDOW_DAYS,
            as_of=baseline_as_of,
        )
        baseline = (
            FactorBaseline(
                mean=baseline_result.mean,
                stddev=baseline_result.stddev,
                n=baseline_result.n,
            )
            if isinstance(baseline_result, Baseline)
            else None
        )
        factors[factor] = FactorObservation(value=value, baseline=baseline)

    usable_days = count_usable_days(session, as_of=as_of)
    return MetricsSnapshot(as_of=as_of, usable_days=usable_days, factors=factors)
