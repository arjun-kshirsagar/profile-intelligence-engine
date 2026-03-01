from typing import Any
from app.logger import logger

WEIGHTS = {
    "experience": 0.30,
    "impact": 0.25,
    "leadership": 0.20,
    "reputation": 0.15,
    "signal_density": 0.10,
}

DECISION_THRESHOLD = 70


def _cap(value: float, max_value: float) -> float:
    if max_value <= 0:
        return 0.0
    return min(max(value / max_value, 0.0), 1.0)


def compute_deterministic_score(signals: dict[str, Any]) -> tuple[int, dict[str, float]]:
    logger.debug(f"Computing deterministic score for signals: {signals}")
    experience = _cap(signals.get("years_experience", 0), 15)

    impact = (
        0.6 * _cap(signals.get("public_repos", 0), 100)
        + 0.4 * _cap(signals.get("followers", 0), 5000)
    )

    leadership = 1.0 if signals.get("has_founder_keyword") else 0.0
    reputation = _cap(signals.get("speaking_mentions", 0), 10)

    density_raw = (
        int(signals.get("public_repos", 0) > 0)
        + int(signals.get("followers", 0) > 0)
        + int(signals.get("years_experience", 0) > 0)
        + int(signals.get("has_founder_keyword", False))
        + int(signals.get("speaking_mentions", 0) > 0)
        + int(signals.get("blog_count", 0) > 0)
        + int(signals.get("twitter_bio_present", False))
    )
    signal_density = density_raw / 7

    components = {
        "experience": experience,
        "impact": impact,
        "leadership": leadership,
        "reputation": reputation,
        "signal_density": signal_density,
    }

    weighted_total = sum(components[k] * WEIGHTS[k] for k in WEIGHTS)
    return round(weighted_total * 100), components


def make_decision(score: int) -> str:
    return "ACCEPT" if score >= DECISION_THRESHOLD else "REJECT"


def default_reasoning(score: int, components: dict[str, float]) -> str:
    strong = [k for k, v in components.items() if v >= 0.65]
    weak = [k for k, v in components.items() if v <= 0.35]

    if score >= DECISION_THRESHOLD:
        if strong:
            return f"Strong signals in {', '.join(strong)}."
        return "Overall profile strength crosses acceptance threshold."

    if weak:
        return f"Limited evidence in {', '.join(weak)} relative to threshold."
    return "Current profile signals do not clear acceptance threshold."
