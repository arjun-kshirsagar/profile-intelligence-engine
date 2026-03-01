from fastapi import Depends, FastAPI
from sqlalchemy.orm import Session

from app.db import get_db
from app.intelligence import build_profile_intelligence
from app.logger import logger
from app.models import (
    Evaluation,
    EvaluationStatus,
    Person,
    ProfileEvaluation,
    ProfileIntelligenceReport,
    ProfileResolutionReport,
)
from app.profile_resolution import resolve_profile
from app.schemas import (
    EvaluationResponse,
    EvaluationStatusEnum,
    IntelligenceInput,
    IntelligenceResponse,
    JobInput,
    JobResponse,
    ProfileInput,
    ResolveProfileInput,
    ResolveProfileResponse,
)
from app.service import evaluate_profile
from app.tasks import run_evaluation_pipeline

app = FastAPI(title="Profile Intelligence Engine", version="0.3.0")


@app.get("/health")
async def health() -> dict[str, str]:
    logger.debug("Health check requested")
    return {"status": "ok"}


@app.post("/evaluate", response_model=EvaluationResponse)
async def evaluate(
    payload: ProfileInput, db: Session = Depends(get_db)
) -> EvaluationResponse:
    logger.info(f"POST /evaluate request received for: {payload.name}")
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
async def intelligence(
    payload: IntelligenceInput, db: Session = Depends(get_db)
) -> IntelligenceResponse:
    logger.info(
        f"POST /intelligence request received for: {payload.name or payload.linkedin_url}"
    )
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


@app.post("/resolve-profile", response_model=ResolveProfileResponse)
async def resolve_profile_endpoint(
    payload: ResolveProfileInput,
    db: Session = Depends(get_db),
) -> ResolveProfileResponse:
    logger.info(
        f"POST /resolve-profile request received for: {payload.name or payload.linkedin_url}"
    )
    result = await resolve_profile(
        linkedin_url=payload.linkedin_url,
        name=payload.name,
        company=payload.company,
        designation=payload.designation,
        location=payload.location,
        max_sources=payload.max_sources,
    )

    resolved_identity = result["resolved_identity"]
    row = ProfileResolutionReport(
        input_payload=payload.model_dump(),
        resolved_name=resolved_identity.get("name"),
        resolved_company=resolved_identity.get("company"),
        resolved_designation=resolved_identity.get("designation"),
        resolved_location=resolved_identity.get("location"),
        resolved_confidence=resolved_identity.get("confidence", 0.0),
        ambiguity_flag=result["ambiguity_flag"],
        clarification_question=result.get("clarification_question"),
        sources=result["sources"],
        aggregated_summary=result["aggregated_summary"],
    )
    db.add(row)
    db.commit()

    return ResolveProfileResponse(**result)


@app.post("/v1/evaluations", response_model=JobResponse)
async def create_evaluation_job(
    payload: JobInput, db: Session = Depends(get_db)
) -> JobResponse:
    logger.info(f"POST /v1/evaluations - received request: {payload.input_type}")

    # 1. Create Person record
    person = db.query(Person).filter(Person.linkedin_url == payload.input_value).first()
    if not person:
        person = Person(
            linkedin_url=(
                payload.input_value if payload.input_type == "linkedin_url" else None
            ),
            github_url=(
                payload.input_value if payload.input_type == "github_url" else None
            ),
        )
        db.add(person)
        db.flush()  # To get the ID for evaluation

    # 2. Create Evaluation record
    evaluation = Evaluation(
        person_id=person.id,
        status=EvaluationStatus.QUEUED,
        stage=None,
    )
    db.add(evaluation)
    db.commit()
    db.refresh(evaluation)

    # 3. Push background job
    run_evaluation_pipeline.delay(evaluation.id)

    return JobResponse(
        evaluation_id=evaluation.id,
        status=EvaluationStatusEnum(evaluation.status.value),
    )


@app.get("/v1/evaluations/{evaluation_id}")
async def get_evaluation_status(
    evaluation_id: int, db: Session = Depends(get_db)
) -> dict:
    evaluation = db.query(Evaluation).get(evaluation_id)
    if not evaluation:
        return {"error": "Evaluation not found"}

    return {
        "evaluation_id": evaluation.id,
        "status": evaluation.status.value,
        "stage": evaluation.stage.value if evaluation.stage else None,
        "final_score": (
            evaluation.final_score
            if evaluation.status == EvaluationStatus.COMPLETED
            else None
        ),
        "decision": (
            evaluation.decision
            if evaluation.status == EvaluationStatus.COMPLETED
            else None
        ),
    }
