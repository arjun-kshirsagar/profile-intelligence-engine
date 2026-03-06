from typing import List, Optional

from pydantic import BaseModel, Field

from app.agents.base import BaseAgent
from app.logger import logger


class ArticleExtractionResult(BaseModel):
    is_about_person: bool = Field(
        description="True if the article is primarily about or significantly mentions the target person."
    )
    achievements: List[str] = Field(
        description="List of specific professional achievements or milestones mentioned."
    )
    sentiment: str = Field(
        description="Overall sentiment regarding the person. Must be 'positive', 'neutral', or 'negative'."
    )
    key_quotes: List[str] = Field(
        description="Up to 3 notable quotes by or about the person from the text."
    )


class ArticleExtractionAgent(BaseAgent):
    """
    Agent responsible for extracting structured signals from raw, unstructured article text.
    """

    def __init__(self, provider: str = "groq", max_retries: int = 2):
        super().__init__(provider=provider, max_retries=max_retries, timeout_seconds=30)

    async def extract(
        self, name: str, article_text: str, source_url: Optional[str] = None
    ) -> ArticleExtractionResult:
        """
        Analyzes messy article text to pull structured achievements and sentiment.
        """
        system_prompt = (
            "You are an expert AI extraction system analyzing news articles and blog posts. "
            "Your job is to extract structured professional signals about a specific person from messy text."
            "\n\nRules:\n"
            "1. First, determine if the article is actually about the person. "
            "If it's a false positive match, set is_about_person to false and leave lists empty.\n"
            "2. Extract concrete achievements (e.g., 'raised $5M', 'launched v2', 'spoke at PyCon'). Be concise.\n"
            "3. Assess the professional sentiment.\n"
            "4. Extract up to 3 impactful quotes if available."
        )

        # Truncate text to avoid massive token usage on huge pages
        truncated_text = article_text[:15000]

        context = f"Target Person: {name}\n"
        if source_url:
            context += f"Source URL: {source_url}\n"

        user_prompt = (
            f"{context}\n\n"
            f"--- ARTICLE TEXT START ---\n"
            f"{truncated_text}\n"
            f"--- ARTICLE TEXT END ---"
        )

        logger.info(
            f"Running ArticleExtractionAgent for {name} on article: {source_url[:50] if source_url else 'Unknown'}"
        )
        try:
            result = await self.execute(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response_model=ArticleExtractionResult,
            )
            return result
        except Exception as e:
            logger.error(f"ArticleExtractionAgent failed for {name}: {e}")
            # Fallback on failure
            return ArticleExtractionResult(
                is_about_person=False,
                achievements=[],
                sentiment="neutral",
                key_quotes=[],
            )
