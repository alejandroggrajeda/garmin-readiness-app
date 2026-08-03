"""Versioned default scoring weights for `compute_readiness`.

v1 weights are estimates (design.md's "Open Questions": "Scoring weights
are v1 estimates to be recalibrated against subjective feel after ~60
days"). Persisting `weights_version` with every score (see
`ReadinessResult.weights_version`) keeps that recalibration auditable
instead of silently changing the meaning of historical scores.
"""

from __future__ import annotations

from app.readiness.types import ScoringWeights

#: v1 factor weights sum to 1.0. Relative ordering (HRV > sleep >
#: resting HR ~= stress > body battery ~= training load) reflects that
#: HRV is the most commonly cited leading indicator of autonomic
#: recovery in the sports-science literature this project draws
#: informal inspiration from, while body battery and training load are
#: kept as smaller, corroborating signals rather than primary drivers --
#: there is no public Garmin formula to copy (design.md), so this is
#: original weighting, deliberately conservative until real usage data
#: supports a v2 recalibration.
DEFAULT_WEIGHTS = ScoringWeights(
    version="v1",
    factor_weights={
        "hrv": 0.30,
        "sleep": 0.20,
        "resting_hr": 0.15,
        "stress": 0.15,
        "body_battery": 0.10,
        "training_load": 0.10,
    },
    factor_polarity={
        "hrv": "higher_is_better",
        "sleep": "higher_is_better",
        "resting_hr": "lower_is_better",
        "stress": "lower_is_better",
        "body_battery": "higher_is_better",
        # ACWR (acute:chronic workload ratio) has no monotonic "more is
        # better" direction -- both overreaching (ratio far above the
        # personal baseline) and undertraining (far below it) are
        # penalized; only staying close to the established baseline load
        # is rewarded, hence `distance_from_target` rather than a
        # higher/lower polarity.
        "training_load": "distance_from_target",
    },
    # 1 stddev of deviation from a factor's personal baseline moves that
    # factor's 0-100 sub-score by 20 points (so roughly +/-2.5 stddev
    # saturates the sub-score at the [0, 100] clamp). Chosen so a single
    # very-off factor is noticeable but a fully-available snapshot with
    # every factor at +/-1 stddev doesn't already max out the scale --
    # a v1 estimate, tunable via a future `weights_version` bump.
    z_to_points_slope=20.0,
    # See engine.py's `_dominant_factors` docstring for the reasoning:
    # day-to-day HRV/sleep/stress noise makes a <0.10 stddev gap an
    # unreliable "more dominant" signal.
    tie_threshold=0.10,
    # design.md: "<60% coverage -> insufficient".
    insufficient_coverage_threshold=0.60,
    # spec.md (readiness-scoring, "Calibrating State"): "While fewer than 60
    # days of baseline-dependent history exist ... return a 'calibrating'
    # state instead of a numeric score." design.md rev2 had drifted to an
    # incorrect 14-day figure (silently, never reconciled against spec.md
    # until sdd-verify caught it); this is now corrected to match spec.md's
    # literal 60-day requirement -- the binary calibrating/scored transition
    # spec.md describes has no 14-59 day partial-confidence range.
    calibrating_below_days=60,
    # design.md: "confidence = usable_days / 60", capped at 1.0 for
    # usable_days >= 60.
    full_confidence_at_days=60,
    # v1 band cutoffs: >=80 train_hard, >=60 moderate, >=40 easy, else
    # rest. A coarse four-band split matching the mobile card's
    # recommendation copy (Phase 7); not derived from any external
    # formula -- recalibrate alongside the factor weights.
    band_thresholds=(80, 60, 40),
)
