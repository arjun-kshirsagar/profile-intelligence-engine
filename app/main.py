from fastapi import Depends, FastAPI
from sqlalchemy.orm import Session

from app.db import Base, engine, get_db
from app.intelligence import build_profile_intelligence
from app.models import ProfileEvaluation, ProfileIntelligenceReport
from app.schemas import (
    EvaluationResponse,
    IntelligenceInput,
    IntelligenceResponse,
    ProfileInput,
)
from app.service import evaluate_profile

app = FastAPI(title="Profile Intelligence Engine", version="0.2.0")


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/evaluate", response_model=EvaluationResponse)
async def evaluate(payload: ProfileInput, db: Session = Depends(get_db)) -> EvaluationResponse:
    result = await evaluate_profile(
        db=db,
        name=payload.name,
        github_url=payload.github_url,
        website_url=payload.website_url,
        twitter_url=payload.twitter_url,
    )

    row = ProfileEvaluation(
        name=payload.name,
        github_url=payload.github_url,
        website_url=payload.website_url,
        twitter_url=payload.twitter_url,
        signals=result["signals"],
        scrape_failures=result["scrape_failures"],
        score=result["score"],
        deterministic_score=result["deterministic_score"],
        llm_score_adjustment=result["llm_score_adjustment"],
        decision=result["decision"],
        reasoning=result["reasoning"],
    )
    db.add(row)
    db.commit()

    return EvaluationResponse(**result)


@app.post("/intelligence", response_model=IntelligenceResponse)
async def intelligence(payload: IntelligenceInput, db: Session = Depends(get_db)) -> IntelligenceResponse:
    result = await build_profile_intelligence(
        linkedin_url=payload.linkedin_url,
        name=payload.name,
        qualifiers=payload.qualifiers,
        max_sources=payload.max_sources,
    )

    row = ProfileIntelligenceReport(
        query_input=result["query"],
        name=payload.name,
        linkedin_url=payload.linkedin_url,
        qualifiers=payload.qualifiers,
        status=result["status"],
        disambiguated=result["disambiguated"],
        clarification_questions=result["clarification_questions"],
        candidates=result["candidates"],
        sources=result["sources"],
        summary=result["summary"],
    )
    db.add(row)
    db.commit()

    return IntelligenceResponse(**result)
