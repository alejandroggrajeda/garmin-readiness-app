"""Z-score / baseline-deviation helpers for the readiness engine.

Extracted from `engine.py` (Phase 4 REFACTOR step) so the core scoring
loop reads as orchestration -- build a contribution per factor, combine,
explain -- rather than interleaved arithmetic. Pure, I/O-free, same as
the rest of `app.readiness`.
"""

from __future__ import annotations

from app.readiness.types import FactorObservation, Polarity


def raw_z_score(observation: FactorObservation | None) -> float | None:
    """Standard z-score of today's value against its personal baseline, or
    `None` if the observation itself, its value, or its baseline is
    missing, or the baseline has zero spread (a degenerate baseline can't
    produce a meaningful deviation and would otherwise divide by zero)."""
    if observation is None or observation.value is None or observation.baseline is None:
        return None
    if observation.baseline.stddev <= 0:
        return None
    return (observation.value - observation.baseline.mean) / observation.baseline.stddev


def effective_z_score(raw_z: float, polarity: Polarity) -> float:
    """Reorients a raw z-score so positive always means "better for
    readiness", per the factor's configured polarity:

    - `higher_is_better` (hrv, sleep, body_battery): unchanged -- a higher
      raw value than baseline already means better.
    - `lower_is_better` (resting_hr, stress): sign-flipped, since a lower
      raw value than baseline is what's good here.
    - `distance_from_target` (training_load / ACWR): neither direction is
      inherently "good" -- only proximity to the personal baseline
      (treated as the ideal load) is, so deviation in either direction is
      penalized via `-abs(raw_z)`. This polarity's best case is neutral
      (0.0, i.e. exactly at baseline), never positive.
    """
    if polarity == "higher_is_better":
        return raw_z
    if polarity == "lower_is_better":
        return -raw_z
    return -abs(raw_z)


def z_to_points(effective_z: float, *, slope: float) -> float:
    """Maps an effective z-score to a 0-100 sub-score centered at 50
    (exactly-at-baseline = neutral). `slope` (points per stddev) is always
    passed in from `ScoringWeights.z_to_points_slope` rather than hardcoded
    here, so it stays a config-versioned knob, not a hidden constant."""
    points = 50.0 + effective_z * slope
    return max(0.0, min(100.0, points))
