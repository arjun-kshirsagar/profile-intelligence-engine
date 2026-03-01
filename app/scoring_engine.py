from typing import Tuple

from sqlalchemy.orm import Session

from app.models import ScoringConfig, Signal


class ScoringEngine:
    """
    Engine responsible for computing the final score based on weighted signals
    and making a decision based on configurable thresholds.
    """

    def __init__(self, db: Session):
        self.db = db
        self.config = self._get_active_config()

    def _get_active_config(self) -> ScoringConfig:
        """Fetch the active scoring configuration from DB."""
        config = (
            self.db.query(ScoringConfig)
            .filter(ScoringConfig.is_active.is_(True))
            .first()
        )
        if not config:
            # Fallback to a default if no active config exists in DB
            return ScoringConfig(
                version="v1.0.default",
                weights_json={
                    "execution": 0.30,
                    "technical_depth": 0.25,
                    "influence": 0.20,
                    "recognition": 0.25,
                },
                thresholds_json={"admit": 80, "manual_review": 65},
            )
        return config

    def compute_and_decide(self, signals: Signal) -> Tuple[float, str, str]:
        """
        Computes final score and returns (score, decision, version).
        """
        weights = self.config.weights_json
        thresholds = self.config.thresholds_json

        # 1. Weighted computation
        final_score = (
            signals.execution_score * weights.get("execution", 0)
            + signals.technical_depth_score * weights.get("technical_depth", 0)
            + signals.influence_score * weights.get("influence", 0)
            + signals.recognition_score * weights.get("recognition", 0)
        )

        # 2. Decision Logic
        if final_score >= thresholds.get("admit", 80):
            decision = "ADMIT"
        elif final_score >= thresholds.get("manual_review", 65):
            decision = "MANUAL_REVIEW"
        else:
            decision = "REJECT"

        return round(final_score, 2), decision, self.config.version
