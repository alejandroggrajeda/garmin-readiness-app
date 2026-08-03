"""Plain, I/O-free data contracts for the readiness scoring engine.

These dataclasses intentionally do NOT reuse `app.store.repositories`'s
`Baseline` / `InsufficientHistory` (even though those are themselves plain
dataclasses) because importing `app.store.repositories` transitively pulls
in `sqlalchemy` -- and design.md requires `app/readiness/engine.py` (and
everything it imports) to have ZERO db/network imports so it stays callable
by future code (PR5's sync endpoint, PR6's readiness-api) as pure logic,
with no I/O boundary anywhere in its import graph.

A thin mapping from `app.store.repositories.Baseline`/`InsufficientHistory`
and `app.store.models.DailyMetric` to `MetricsSnapshot` is Phase 6 scope
(readiness-api), not this module's job.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Literal

#: The six readiness factors this engine scores -- the exact subset of
#: `daily_metrics` columns (see app/store/models.py) design.md's Data
#: Model names as readiness-relevant: HRV vs. baseline, sleep score,
#: resting HR (recovery), stress, body battery, and training
#: load/ACWR. Named individually (rather than scored as one opaque blob)
#: because readiness-scoring's "Reason Explanation" and "Degraded Mode"
#: requirements both need per-factor visibility.
FactorName = Literal[
    "hrv", "sleep", "resting_hr", "stress", "body_battery", "training_load"
]

State = Literal["scored", "calibrating", "insufficient"]
Band = Literal["train_hard", "moderate", "easy", "rest"]
Polarity = Literal["higher_is_better", "lower_is_better", "distance_from_target"]


@dataclass(frozen=True)
class FactorBaseline:
    """A personal baseline for one factor -- the mean/stddev today's value
    is compared against. `n` (observation count) is carried for audit only;
    the engine trusts the caller already resolved "insufficient history"
    upstream (see `app.store.repositories.get_rolling_baseline`) -- a
    factor with no `FactorBaseline` here is simply unavailable to score,
    see `MetricsSnapshot`."""

    mean: float
    stddev: float
    n: int


@dataclass(frozen=True)
class FactorObservation:
    """Today's raw value for one factor plus the baseline it is compared
    against. `value` and `baseline` are independently `None`-able -- a day
    can have a value but no baseline yet (cold start) or, in principle, a
    baseline but a missing today reading (degraded mode); either case makes
    the factor unavailable for scoring."""

    value: float | None
    baseline: FactorBaseline | None = None


@dataclass(frozen=True)
class MetricsSnapshot:
    """Pure input to `compute_readiness`. Mirrors design.md's sketch
    ("today's DailyMetrics + Baseline (7/28/60d) + usable_days: int") but
    as engine-owned plain types instead of store/SQLAlchemy types, so this
    module never imports `app.store.*`."""

    as_of: dt.date
    usable_days: int
    factors: dict[FactorName, FactorObservation]


@dataclass(frozen=True)
class ScoringWeights:
    """Config-versioned scoring configuration. Every numeric knob the
    algorithm uses lives here -- never as a magic number inside
    `engine.py` -- so a future recalibration (design.md's "Open
    Questions": weights are v1 estimates to be recalibrated after ~60
    days of real data) is an auditable new `version` string persisted
    alongside every stored score as `weights_version`."""

    version: str
    factor_weights: dict[FactorName, float]
    factor_polarity: dict[FactorName, Polarity]
    z_to_points_slope: float
    tie_threshold: float
    insufficient_coverage_threshold: float
    calibrating_below_days: int
    full_confidence_at_days: int
    #: (train_hard_at, moderate_at, easy_at) -- inclusive lower bounds;
    #: below `easy_at` is "rest".
    band_thresholds: tuple[int, int, int]


@dataclass(frozen=True)
class FactorContribution:
    """One factor's role in a result. `available=False` means the factor
    was missing today's value and/or its baseline and was excluded from
    scoring (its weight redistributed among the rest) -- this is how
    readiness-scoring's "Degraded Mode for Missing Factors" requirement
    surfaces which factor(s) are unavailable to the caller. `weight` is
    always the factor's *configured* weight (not the redistributed one)
    so callers can see how much of the total was missing."""

    name: FactorName
    available: bool
    z_value: float | None
    weight: float
    points: float | None


@dataclass(frozen=True)
class ReadinessResult:
    """Output of `compute_readiness` -- see design.md's `ReadinessEngine`
    decision. `dominant_factor` is a single comma-joined string (e.g.
    `"hrv"` or `"hrv, body_battery"`) rather than a list, so a tie is
    represented without widening the field's type: readiness-scoring's
    "Tied dominant factors" scenario requires ALL tied factors to be
    named, never an arbitrary pick."""

    state: State
    score: int | None
    band: Band | None
    factors: tuple[FactorContribution, ...]
    dominant_factor: str | None
    reason: str
    confidence: float
    weights_version: str
    #: Only set while `state == "calibrating"` -- how many more usable
    #: days are needed before scoring starts (readiness-scoring's "Cold
    #: start" scenario: "days-remaining shown, and no score is
    #: returned"). Not part of design.md's original sketch; added because
    #: the spec scenario requires it and `reason` alone is prose, not a
    #: value a client can format/pluralize.
    days_until_scored: int | None = None
