import asyncio
import time
from datetime import datetime

from sqlalchemy.orm import Session

from app.celery_app import celery_app
from app.collectors.github_collector import GitHubCollector
from app.collectors.linkedin_collector import LinkedInCollector
from app.collectors.web_search_collector import WebSearchCollector
from app.db import SessionLocal
from app.logger import logger
from app.models import Evaluation, EvaluationStage, EvaluationStatus


@celery_app.task(
    bind=True,
    name="app.tasks.run_evaluation_pipeline",
    max_retries=3,
    default_retry_delay=60,
)
def run_evaluation_pipeline(self, evaluation_id: int):
    """
    Background task to run the full evaluation pipeline.
    """
    db: Session = SessionLocal()
    try:
        evaluation = db.query(Evaluation).get(evaluation_id)
        if not evaluation:
            logger.error(f"Evaluation {evaluation_id} not found")
            return

        person = evaluation.person
        evaluation.status = EvaluationStatus.IN_PROGRESS
        evaluation.started_at = datetime.utcnow()
        db.commit()

        # Phase 1: Identity Resolution
        _update_stage(db, evaluation, EvaluationStage.IDENTITY_RESOLUTION)
        # TODO: Implement real identity resolution
        time.sleep(1)

        # Phase 2: Data Collection
        _update_stage(db, evaluation, EvaluationStage.DATA_COLLECTION)

        # Run collectors in an event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            results = loop.run_until_complete(
                _run_collectors(
                    person.linkedin_url, person.github_url or person.full_name
                )
            )

            # Store raw JSON in Person record
            person.metadata_json = results

            # Optionally update person fields from LinkedIn mock data
            li_data = next(
                (r["raw_data"] for r in results if r["source"] == "linkedin"), {}
            )
            if li_data:
                person.full_name = li_data.get("full_name", person.full_name)
                person.current_role = li_data.get("current_role", person.current_role)
                person.current_company = li_data.get(
                    "current_company", person.current_company
                )

            db.commit()
        finally:
            loop.close()

        # Phase 3: Signal Extraction
        _update_stage(db, evaluation, EvaluationStage.SIGNAL_EXTRACTION)
        # TODO: Implement signal extraction logic
        time.sleep(1)

        # Phase 4: Scoring
        _update_stage(db, evaluation, EvaluationStage.SCORING)
        # TODO: Implement scoring logic
        time.sleep(1)

        # Phase 5: Decision
        _update_stage(db, evaluation, EvaluationStage.DECISION)
        # TODO: Implement decision logic
        evaluation.status = EvaluationStatus.COMPLETED
        evaluation.completed_at = datetime.utcnow()
        db.commit()

    except Exception as exc:
        logger.exception(f"Error in evaluation pipeline for ID {evaluation_id}")
        evaluation.status = EvaluationStatus.FAILED
        db.commit()
        raise self.retry(exc=exc)
    finally:
        db.close()


async def _run_collectors(linkedin_url: str, github_input: str):
    """Utility to run multiple collectors concurrently."""
    li_collector = LinkedInCollector()
    gh_collector = GitHubCollector()
    ws_collector = WebSearchCollector()

    tasks = [
        li_collector.collect(linkedin_url),
        gh_collector.collect(github_input),
        ws_collector.collect(f"{github_input} news"),
    ]

    return await asyncio.gather(*tasks)


def _update_stage(db: Session, evaluation: Evaluation, stage: EvaluationStage):
    logger.info(f"Transitioning evaluation {evaluation.id} to stage {stage.value}")
    evaluation.stage = stage
    db.commit()
