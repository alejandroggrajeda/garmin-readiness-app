"""Pure readiness scoring core (readiness-scoring capability, Phase 4).

ZERO db/network imports by design -- see design.md's `ReadinessEngine`
decision: "imports nothing from `db/`, `garmin/` or `api/`". Nothing in
this module's import graph (`app.readiness.types`, `.weights`,
`.baselines`) touches SQLAlchemy, `garminconnect`, or the network, so
`compute_readiness` is safe to call from anywhere -- including a future
sync endpoint (PR5) or API route (PR6) -- with no I/O side effects.

`compute_readiness` is a pure function: identical `MetricsSnapshot` +
`ScoringWeights` in always produces an identical `ReadinessResult` out
(readiness-scoring's "Pure Function Contract" requirement) -- no clock
reads, no randomness, no hidden state. Dict iteration order is relied on
for determinism (Python dicts preserve insertion order), so contribution
order always follows `weights.factor_weights`'s declared order.
"""

from __future__ import annotations

from app.readiness.baselines import effective_z_score, raw_z_score, z_to_points
from app.readiness.types import (
    Band,
    FactorContribution,
    FactorName,
    MetricsSnapshot,
    ReadinessResult,
    ScoringWeights,
)


def compute_readiness(
    snapshot: MetricsSnapshot, weights: ScoringWeights
) -> ReadinessResult:
    """Score `snapshot` per `weights`. See readiness-scoring's four
    requirements for the exact contract: pure-function determinism,
    calibrating state below `weights.calibrating_below_days` usable days,
    a dominant-factor reason sentence (with tie-listing), and re-weighted
    degraded-mode scoring that falls back to "insufficient" below
    `weights.insufficient_coverage_threshold` weight coverage.
    """
    if snapshot.usable_days < weights.calibrating_below_days:
        return _calibrating_result(snapshot, weights)

    contributions = _build_contributions(snapshot, weights)
    total_weight = sum(weights.factor_weights.values())
    available_weight = sum(c.weight for c in contributions if c.available)
    coverage = available_weight / total_weight if total_weight > 0 else 0.0

    if coverage < weights.insufficient_coverage_threshold:
        return _insufficient_result(contributions, weights, snapshot.usable_days)

    return _scored_result(contributions, available_weight, weights, snapshot.usable_days)


def _calibrating_result(
    snapshot: MetricsSnapshot, weights: ScoringWeights
) -> ReadinessResult:
    days_remaining = weights.calibrating_below_days - snapshot.usable_days
    return ReadinessResult(
        state="calibrating",
        score=None,
        band=None,
        factors=(),
        dominant_factor=None,
        reason=(
            f"Calibrating: {days_remaining} more day(s) of history needed "
            "before a score is available."
        ),
        confidence=0.0,
        weights_version=weights.version,
        days_until_scored=days_remaining,
    )


def _insufficient_result(
    contributions: tuple[FactorContribution, ...],
    weights: ScoringWeights,
    usable_days: int,
) -> ReadinessResult:
    missing = sorted(c.name for c in contributions if not c.available)
    return ReadinessResult(
        state="insufficient",
        score=None,
        band=None,
        factors=contributions,
        dominant_factor=None,
        reason=(
            "Not enough of today's factors are available to score "
            f"readiness (missing: {', '.join(missing)})."
        ),
        confidence=_confidence(usable_days, weights.full_confidence_at_days),
        weights_version=weights.version,
    )


def _scored_result(
    contributions: tuple[FactorContribution, ...],
    available_weight: float,
    weights: ScoringWeights,
    usable_days: int,
) -> ReadinessResult:
    score = _weighted_score(contributions, available_weight)
    band = _band_for_score(score, weights.band_thresholds)
    dominant_names = _dominant_factors(contributions, weights.tie_threshold)
    reason = _build_reason(dominant_names, contributions)

    return ReadinessResult(
        state="scored",
        score=score,
        band=band,
        factors=contributions,
        dominant_factor=", ".join(dominant_names) if dominant_names else None,
        reason=reason,
        confidence=_confidence(usable_days, weights.full_confidence_at_days),
        weights_version=weights.version,
    )


def _build_contributions(
    snapshot: MetricsSnapshot, weights: ScoringWeights
) -> tuple[FactorContribution, ...]:
    contributions: list[FactorContribution] = []
    for name, configured_weight in weights.factor_weights.items():
        observation = snapshot.factors.get(name)
        raw_z = raw_z_score(observation)
        if raw_z is None:
            contributions.append(
                FactorContribution(
                    name=name,
                    available=False,
                    z_value=None,
                    weight=configured_weight,
                    points=None,
                )
            )
            continue

        polarity = weights.factor_polarity[name]
        eff_z = effective_z_score(raw_z, polarity)
        points = z_to_points(eff_z, slope=weights.z_to_points_slope)
        contributions.append(
            FactorContribution(
                name=name,
                available=True,
                z_value=eff_z,
                weight=configured_weight,
                points=points,
            )
        )
    return tuple(contributions)


def _weighted_score(
    contributions: tuple[FactorContribution, ...], available_weight: float
) -> int:
    total_points = sum(
        (c.weight / available_weight) * c.points
        for c in contributions
        if c.available and c.points is not None
    )
    return max(0, min(100, round(total_points)))


def _band_for_score(score: int, thresholds: tuple[int, int, int]) -> Band:
    train_hard_at, moderate_at, easy_at = thresholds
    if score >= train_hard_at:
        return "train_hard"
    if score >= moderate_at:
        return "moderate"
    if score >= easy_at:
        return "easy"
    return "rest"


def _dominant_factors(
    contributions: tuple[FactorContribution, ...], tie_threshold: float
) -> tuple[FactorName, ...]:
    """The factor(s) with the largest |effective z-score| among available
    factors -- the biggest driver of the score away from neutral, in
    either direction. Ties (within `tie_threshold` stddev of the maximum)
    are ALL listed rather than arbitrarily picking one, per
    readiness-scoring's "Tied dominant factors" scenario.

    `tie_threshold = 0.10` (see weights.py) was chosen because day-to-day
    HRV/sleep/stress readings carry enough measurement noise that a
    0.10-stddev gap between two factors is not a reliably distinguishable
    "more dominant" signal -- treating it as a tie avoids an
    arbitrary-feeling single-factor callout for what is, in effect, an
    equally significant pair (or more) of readings.
    """
    available = [c for c in contributions if c.available and c.z_value is not None]
    if not available:
        return ()

    magnitudes = {c.name: abs(c.z_value) for c in available}  # type: ignore[arg-type]
    max_magnitude = max(magnitudes.values())
    tied = [
        name
        for name in magnitudes  # preserves contribution order, not set/dict-hash order
        if max_magnitude - magnitudes[name] <= tie_threshold
    ]
    return tuple(tied)


def _build_reason(
    dominant_names: tuple[FactorName, ...],
    contributions: tuple[FactorContribution, ...],
) -> str:
    if not dominant_names:
        return "No factors were available to explain today's score."

    by_name = {c.name: c for c in contributions}
    labels = [_direction_label(by_name[name]) for name in dominant_names]
    if len(labels) == 1:
        return f"{labels[0]} is today's dominant factor."
    return f"{' and '.join(labels)} are tied as today's dominant factors."


def _direction_label(contribution: FactorContribution) -> str:
    assert contribution.z_value is not None
    direction = "above" if contribution.z_value >= 0 else "below"
    pretty = contribution.name.replace("_", " ")
    return f"{pretty} ({direction} your baseline)"


def _confidence(usable_days: int, full_confidence_at_days: int) -> float:
    if usable_days >= full_confidence_at_days:
        return 1.0
    return usable_days / full_confidence_at_days
