from typing import Any, Dict, List

from pydantic import BaseModel, Field

from app.agents.base import BaseAgent
from app.logger import logger


class ExplanationResult(BaseModel):
    summary: str = Field(
        description=(
            "A concise 2-3 sentence summary explaining the person's professional "
            "standing and why they received their score."
        )
    )
    strengths: List[str] = Field(
        description="Top 2-3 professional strengths based strictly on the provided signals."
    )
    weaknesses: List[str] = Field(
        description="Top 1-2 areas for improvement or missing signals based strictly on the provided signals."
    )


class ExplanationAgent(BaseAgent):
    """
    Agent responsible for translating deterministic scores and signals into a human-readable explanation.
    """

    def __init__(self, provider: str = "groq", max_retries: int = 2):
        super().__init__(provider=provider, max_retries=max_retries, timeout_seconds=20)

    async def generate_explanation(
        self,
        name: str,
        final_score: float,
        decision: str,
        execution_score: float,
        technical_depth_score: float,
        influence_score: float,
        recognition_score: float,
        raw_features: Dict[str, Any],
    ) -> ExplanationResult:
        """
        Generates a human-readable synthesis of the pipeline's evaluation.
        """
        system_prompt = (
            "You are a Senior Talent Intelligence Analyst. "
            "Your job is to explain a candidate's automated evaluation score to a hiring manager or investor."
            "\n\nRules:\n"
            "1. Be objective, precise, and professional. Avoid hyperbole.\n"
            "2. Base your explanation strictly on the provided score breakdown and raw features.\n"
            "3. Do not invent facts."
            "\nScore Rubric details:\n"
            "- >=80 is ADMIT (Top 1%)\n"
            "- 65-79 is MANUAL_REVIEW (Strong, but needs human check)\n"
            "- <65 is REJECT"
        )

        user_prompt = (
            f"Candidate: {name}\n"
            f"Final Score: {final_score}/100\n"
            f"Automated Decision: {decision}\n\n"
            f"--- Score Breakdown ---\n"
            f"Execution (Tenure/Roles): {execution_score}/100\n"
            f"Technical Depth (GitHub/Code): {technical_depth_score}/100\n"
            f"Influence (Media/Following): {influence_score}/100\n"
            f"Recognition (Awards/Talks): {recognition_score}/100\n\n"
            f"--- Extracted Raw Features ---\n"
            f"{raw_features}"
        )

        logger.info(f"Running ExplanationAgent for {name} (Score: {final_score})")
        try:
            result = await self.execute(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response_model=ExplanationResult,
            )
            return result
        except Exception as e:
            logger.error(f"ExplanationAgent failed for {name}: {e}")
            # Fallback on failure
            return ExplanationResult(
                summary="System evaluation completed. Automated explanation generation failed.",
                strengths=["Data successfully collected."],
                weaknesses=["Explanation engine timed out or failed."],
            )
