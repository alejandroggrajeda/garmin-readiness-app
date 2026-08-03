"""Unit tests for the pure readiness scoring engine (readiness-scoring
capability, Phase 4). Table-driven golden cases — zero mocks, zero I/O,
since `compute_readiness` is a pure function over plain dataclasses.

Golden numbers are computed by hand in test docstrings/comments so a
regression is caught precisely, not just qualitatively.
"""

from __future__ import annotations

import copy
import datetime as dt

import pytest

from app.readiness.engine import compute_readiness
from app.readiness.types import (
    FactorBaseline,
    FactorObservation,
    MetricsSnapshot,
    ScoringWeights,
)
from app.readiness.weights import DEFAULT_WEIGHTS

AS_OF = dt.date(2026, 8, 2)


def _baseline(mean: float = 50.0, stddev: float = 10.0, n: int = 60) -> FactorBaseline:
    return FactorBaseline(mean=mean, stddev=stddev, n=n)


def _snapshot(
    usable_days: int, values: dict[str, float | None]
) -> MetricsSnapshot:
    """Builds a snapshot where every named factor gets a baseline of
    mean=50/stddev=10 and the given today value; a value of `None` means
    "missing today" (degraded mode), and a factor omitted from `values`
    entirely is also treated as unavailable."""
    factors = {}
    for name in DEFAULT_WEIGHTS.factor_weights:
        value = values.get(name)
        factors[name] = FactorObservation(
            value=value, baseline=_baseline() if value is not None else None
        )
    return MetricsSnapshot(as_of=AS_OF, usable_days=usable_days, factors=factors)


# ---------------------------------------------------------------------------
# Calibrating state (cold start, <60 usable days — spec.md's literal
# "fewer than 60 days of baseline-dependent history" requirement)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("usable_days", "expected_days_remaining"),
    [(0, 60), (5, 55), (13, 47), (14, 46), (59, 1)],
)
def test_cold_start_returns_calibrating_with_days_remaining(
    usable_days: int, expected_days_remaining: int
) -> None:
    snapshot = _snapshot(usable_days, {"hrv": 70})
    result = compute_readiness(snapshot, DEFAULT_WEIGHTS)

    assert result.state == "calibrating"
    assert result.score is None
    assert result.band is None
    assert result.factors == ()
    assert result.dominant_factor is None
    assert result.days_until_scored == expected_days_remaining
    assert result.confidence == 0.0
    assert result.weights_version == DEFAULT_WEIGHTS.version


def test_fourteen_usable_days_is_still_calibrating() -> None:
    """14 usable days is well inside the calibrating range per spec.md's
    60-day "Cold start" scenario. design.md rev2 had drifted to a 14-day
    boundary (now corrected); 14 usable days must NOT produce a score."""
    snapshot = _snapshot(14, {name: 50 for name in DEFAULT_WEIGHTS.factor_weights})
    result = compute_readiness(snapshot, DEFAULT_WEIGHTS)

    assert result.state == "calibrating"
    assert result.score is None


def test_sixty_usable_days_transitions_to_scored() -> None:
    """spec.md's "Transition to scored state" scenario: at exactly 60 days
    of history the result becomes a numeric score with breakdown and band —
    the only transition boundary the spec describes (no 14-59 day partial
    range)."""
    snapshot = _snapshot(60, {name: 50 for name in DEFAULT_WEIGHTS.factor_weights})
    result = compute_readiness(snapshot, DEFAULT_WEIGHTS)

    assert result.state == "scored"
    assert result.score is not None
    assert result.band is not None
    assert result.confidence == 1.0


# ---------------------------------------------------------------------------
# Confidence: full (1.0) as soon as scoring starts. Since
# `calibrating_below_days` and `full_confidence_at_days` are both 60, there
# is no 14-59 day partial-confidence gradient — spec.md only describes a
# binary calibrating/scored transition at 60 days, not a partial range.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "usable_days",
    [60, 90, 365],
)
def test_confidence_is_full_once_scoring_starts(usable_days: int) -> None:
    snapshot = _snapshot(usable_days, {name: 50 for name in DEFAULT_WEIGHTS.factor_weights})
    result = compute_readiness(snapshot, DEFAULT_WEIGHTS)

    assert result.confidence == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Normal scoring — hand-computed golden case
# ---------------------------------------------------------------------------


def test_normal_scoring_produces_the_hand_computed_score_band_and_reason() -> None:
    """All baselines are mean=50/stddev=10. Per-factor raw z, polarity-
    adjusted effective z, and points (50 + effective_z * 20, clamped
    [0,100]):

    | factor        | value | raw_z | polarity              | eff_z | points |
    |---------------|-------|-------|------------------------|-------|--------|
    | hrv           | 70    | 2.0   | higher_is_better       | 2.0   | 90     |
    | sleep         | 60    | 1.0   | higher_is_better       | 1.0   | 70     |
    | resting_hr    | 40    | -1.0  | lower_is_better        | 1.0   | 70     |
    | stress        | 60    | 1.0   | lower_is_better        | -1.0  | 30     |
    | body_battery  | 35    | -1.5  | higher_is_better       | -1.5  | 20     |
    | training_load | 55    | 0.5   | distance_from_target   | -0.5  | 40     |

    Weighted score = 0.30*90 + 0.20*70 + 0.15*70 + 0.15*30 + 0.10*20 + 0.10*40
                    = 27 + 14 + 10.5 + 4.5 + 2 + 4 = 62.0 -> round(62) = 62.
    Band thresholds (80, 60, 40): 62 >= 60 -> "moderate".
    Dominant factor: |eff_z| per factor = hrv 2.0, sleep 1.0, resting_hr 1.0,
    stress 1.0, body_battery 1.5, training_load 0.5. Max is hrv's 2.0 alone
    (next closest, body_battery, is 0.5 away > the 0.10 tie threshold) ->
    single dominant factor, "hrv".
    """
    snapshot = _snapshot(
        usable_days=90,
        values={
            "hrv": 70,
            "sleep": 60,
            "resting_hr": 40,
            "stress": 60,
            "body_battery": 35,
            "training_load": 55,
        },
    )
    result = compute_readiness(snapshot, DEFAULT_WEIGHTS)

    assert result.state == "scored"
    assert result.score == 62
    assert result.band == "moderate"
    assert result.dominant_factor == "hrv"
    assert "hrv" in result.reason
    assert result.confidence == 1.0
    assert len(result.factors) == 6
    assert all(c.available for c in result.factors)


@pytest.mark.parametrize(
    ("score_values", "expected_band"),
    [
        # every factor exactly at baseline -> eff_z 0 for all but
        # training_load's distance_from_target polarity also yields 0 at
        # the baseline mean -> points 50 everywhere -> score 50 -> "easy".
        ({name: 50 for name in DEFAULT_WEIGHTS.factor_weights}, "easy"),
    ],
)
def test_band_boundaries_are_derived_from_score(
    score_values: dict[str, float], expected_band: str
) -> None:
    snapshot = _snapshot(usable_days=90, values=score_values)
    result = compute_readiness(snapshot, DEFAULT_WEIGHTS)

    assert result.score == 50
    assert result.band == expected_band


# ---------------------------------------------------------------------------
# Tied dominant factors
# ---------------------------------------------------------------------------


def test_tied_dominant_factors_are_all_listed_not_arbitrarily_picked() -> None:
    """hrv and body_battery both land on |eff_z| = 2.0 exactly (a 0.0 gap,
    well within the 0.10 tie threshold) while every other factor is at
    least 0.5 away from that maximum, so both — and only both — must be
    named."""
    snapshot = _snapshot(
        usable_days=90,
        values={
            "hrv": 70,  # raw_z 2.0, higher_is_better -> eff_z 2.0
            "sleep": 60,  # raw_z 1.0, higher_is_better -> eff_z 1.0
            "resting_hr": 40,  # raw_z -1.0, lower_is_better -> eff_z 1.0
            "stress": 60,  # raw_z 1.0, lower_is_better -> eff_z -1.0
            "body_battery": 30,  # raw_z -2.0, higher_is_better -> eff_z -2.0
            "training_load": 55,  # raw_z 0.5, distance -> eff_z -0.5
        },
    )
    result = compute_readiness(snapshot, DEFAULT_WEIGHTS)

    assert result.state == "scored"
    assert result.dominant_factor == "hrv, body_battery"
    assert "hrv" in result.reason
    assert "body battery" in result.reason  # reason prose spaces out the name


def test_a_near_but_not_tied_factor_is_excluded() -> None:
    """body_battery's |eff_z| is 1.5 vs hrv's 2.0 -- a 0.5 gap, outside the
    0.10 tie threshold -- so only hrv is named."""
    snapshot = _snapshot(
        usable_days=90,
        values={
            "hrv": 70,
            "sleep": 60,
            "resting_hr": 40,
            "stress": 60,
            "body_battery": 35,
            "training_load": 55,
        },
    )
    result = compute_readiness(snapshot, DEFAULT_WEIGHTS)

    assert result.dominant_factor == "hrv"


# ---------------------------------------------------------------------------
# Degraded mode: one factor missing, re-weighted and flagged
# ---------------------------------------------------------------------------


def test_one_missing_factor_is_re_weighted_and_flagged_unavailable() -> None:
    """Dropping stress (weight 0.15) leaves 0.85 of total weight available
    -- still >= the 0.60 coverage threshold, so scoring proceeds with the
    remaining five factors re-weighted, and `stress`'s contribution is
    flagged `available=False`."""
    snapshot = _snapshot(
        usable_days=90,
        values={
            "hrv": 70,
            "sleep": 60,
            "resting_hr": 40,
            # stress omitted entirely -> unavailable
            "body_battery": 35,
            "training_load": 55,
        },
    )
    result = compute_readiness(snapshot, DEFAULT_WEIGHTS)

    assert result.state == "scored"
    stress_contribution = next(c for c in result.factors if c.name == "stress")
    assert stress_contribution.available is False
    assert stress_contribution.z_value is None
    assert stress_contribution.points is None
    assert "stress" not in (result.dominant_factor or "")


# ---------------------------------------------------------------------------
# Insufficient-coverage threshold boundary (<60% of weight available)
# ---------------------------------------------------------------------------


def test_exactly_sixty_percent_coverage_still_scores() -> None:
    """hrv (0.30) + sleep (0.20) + body_battery (0.10) = exactly 0.60 ->
    the `< 0.60` check does not trip, so this still scores."""
    snapshot = _snapshot(
        usable_days=90,
        values={"hrv": 70, "sleep": 60, "body_battery": 35},
    )
    result = compute_readiness(snapshot, DEFAULT_WEIGHTS)

    assert result.state == "scored"


def test_below_sixty_percent_coverage_is_insufficient() -> None:
    """hrv (0.30) + sleep (0.20) = 0.50 of total weight -- below the 0.60
    threshold -- so no score is produced."""
    snapshot = _snapshot(usable_days=90, values={"hrv": 70, "sleep": 60})
    result = compute_readiness(snapshot, DEFAULT_WEIGHTS)

    assert result.state == "insufficient"
    assert result.score is None
    assert result.band is None
    assert result.dominant_factor is None
    assert "resting_hr" in result.reason


# ---------------------------------------------------------------------------
# Pure-function determinism
# ---------------------------------------------------------------------------


def test_same_input_twice_yields_an_identical_result() -> None:
    snapshot = _snapshot(
        usable_days=90,
        values={
            "hrv": 70,
            "sleep": 60,
            "resting_hr": 40,
            "stress": 60,
            "body_battery": 35,
            "training_load": 55,
        },
    )
    weights = copy.deepcopy(DEFAULT_WEIGHTS)

    first = compute_readiness(snapshot, weights)
    second = compute_readiness(copy.deepcopy(snapshot), copy.deepcopy(weights))

    assert first == second


def test_determinism_holds_across_all_states() -> None:
    """Same property, but exercised for calibrating and insufficient
    states too -- no hidden clock/random/global-state dependency
    anywhere in the engine."""
    calibrating_snapshot = _snapshot(5, {"hrv": 70})
    insufficient_snapshot = _snapshot(90, {"hrv": 70, "sleep": 60})

    for snapshot in (calibrating_snapshot, insufficient_snapshot):
        first = compute_readiness(copy.deepcopy(snapshot), DEFAULT_WEIGHTS)
        second = compute_readiness(copy.deepcopy(snapshot), DEFAULT_WEIGHTS)
        assert first == second


def test_custom_weights_version_is_propagated_onto_the_result() -> None:
    custom = ScoringWeights(
        version="test-v2",
        factor_weights=dict(DEFAULT_WEIGHTS.factor_weights),
        factor_polarity=dict(DEFAULT_WEIGHTS.factor_polarity),
        z_to_points_slope=DEFAULT_WEIGHTS.z_to_points_slope,
        tie_threshold=DEFAULT_WEIGHTS.tie_threshold,
        insufficient_coverage_threshold=DEFAULT_WEIGHTS.insufficient_coverage_threshold,
        calibrating_below_days=DEFAULT_WEIGHTS.calibrating_below_days,
        full_confidence_at_days=DEFAULT_WEIGHTS.full_confidence_at_days,
        band_thresholds=DEFAULT_WEIGHTS.band_thresholds,
    )
    snapshot = _snapshot(90, {name: 50 for name in DEFAULT_WEIGHTS.factor_weights})

    result = compute_readiness(snapshot, custom)

    assert result.weights_version == "test-v2"
