from typing import Optional

from pydantic import BaseModel, Field, model_validator


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


class IntelligenceInput(BaseModel):
    linkedin_url: Optional[str] = None
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    qualifiers: list[str] = Field(default_factory=list, max_length=8)
    max_sources: int = Field(default=12, ge=3, le=25)

    @model_validator(mode="after")
    def validate_payload(self) -> "IntelligenceInput":
        if not self.linkedin_url and not self.name:
            raise ValueError("Either linkedin_url or name must be provided.")
        return self


class SourceRecord(BaseModel):
    source: str
    url: str
    title: str
    snippet: str
    text: str
    confidence: float


class CandidateRecord(BaseModel):
    label: str
    confidence: float
    profile_url: Optional[str] = None
    company_hint: Optional[str] = None
    evidence: list[str] = Field(default_factory=list)


class IntelligenceResponse(BaseModel):
    status: str
    query: str
    disambiguated: bool
    clarification_questions: list[str]
    candidates: list[CandidateRecord]
    sources: list[SourceRecord]
    summary: str
