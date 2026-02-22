from typing import Optional

from pydantic import BaseModel, Field


class ProfileInput(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    github_url: Optional[str] = None
    website_url: Optional[str] = None
    twitter_url: Optional[str] = None


class EvaluationResponse(BaseModel):
    score: int
    decision: str
    reasoning: str
    deterministic_score: int
    llm_score_adjustment: int
    signals: dict
    scrape_failures: list[dict]
