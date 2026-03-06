from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.agents.base import BaseAgent
from app.logger import logger


class IdentityResolutionResult(BaseModel):
    github_url: Optional[str] = Field(
        description="The most likely GitHub profile URL, or null if none found."
    )
    twitter_url: Optional[str] = Field(
        description="The most likely Twitter/X profile URL, or null if none found."
    )
    confidence_score: float = Field(
        description="Confidence score from 0.0 to 1.0 of this match."
    )
    reasoning: str = Field(
        description="Brief explanation of why these profiles were selected or rejected."
    )


class IdentityResolutionAgent(BaseAgent):
    """
    Agent responsible for taking sparse input identifying a person and matching
    them to their canonical social profiles (GitHub, Twitter) from search results.
    """

    def __init__(self, provider: str = "openai", max_retries: int = 2):
        super().__init__(provider=provider, max_retries=max_retries, timeout_seconds=20)

    async def resolve(
        self,
        name: str,
        company: Optional[str],
        role: Optional[str],
        search_results: List[Dict[str, Any]],
    ) -> IdentityResolutionResult:
        """
        Analyzes search results to find the canonical GitHub and Twitter URLs for the person.
        """
        system_prompt = (
            "You are an expert open-source intelligence (OSINT) analyst. "
            "Your job is to identify a specific person's canonical GitHub and Twitter profiles "
            "from a list of raw search results."
            "\n\nRules:\n"
            "1. Be extremely rigorous. If you are not confident a profile "
            "belongs to the exact target person, return null.\n"
            "2. Pay attention to matching names, companies, locations, and roles.\n"
            "3. Provide a clear, concise reasoning trace for your decision.\n"
            "4. Return a confidence score between 0.0 and 1.0."
        )

        target_info = f"Name: {name}\n"
        if company:
            target_info += f"Company: {company}\n"
        if role:
            target_info += f"Role: {role}\n"

        user_prompt = (
            f"Target Person:\n{target_info}\n\n"
            f"Search Results Context:\n{search_results}"
        )

        logger.info(f"Running IdentityResolutionAgent for {name}")
        try:
            result = await self.execute(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response_model=IdentityResolutionResult,
            )
            return result
        except Exception as e:
            logger.error(f"IdentityResolutionAgent failed for {name}: {e}")
            # Fallback on failure
            return IdentityResolutionResult(
                github_url=None,
                twitter_url=None,
                confidence_score=0.0,
                reasoning=f"Agent resolution failed: {str(e)}",
            )
