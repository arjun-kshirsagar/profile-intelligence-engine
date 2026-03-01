import time
from datetime import datetime

from sqlalchemy.orm import Session

from app.celery_app import celery_app
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

        evaluation.status = EvaluationStatus.IN_PROGRESS
        evaluation.started_at = datetime.utcnow()
        db.commit()

        # Phase 1: Identity Resolution
        _update_stage(db, evaluation, EvaluationStage.IDENTITY_RESOLUTION)
        # TODO: Implement identity resolution logic
        time.sleep(1)  # Simulated work

        # Phase 2: Data Collection
        _update_stage(db, evaluation, EvaluationStage.DATA_COLLECTION)
        # TODO: Implement data collection logic
        time.sleep(2)  # Simulated work

        # Phase 3: Signal Extraction
        _update_stage(db, evaluation, EvaluationStage.SIGNAL_EXTRACTION)
        # TODO: Implement signal extraction logic
        time.sleep(1)  # Simulated work

        # Phase 4: Scoring
        _update_stage(db, evaluation, EvaluationStage.SCORING)
        # TODO: Implement scoring logic
        time.sleep(1)  # Simulated work

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


def _update_stage(db: Session, evaluation: Evaluation, stage: EvaluationStage):
    logger.info(f"Transitioning evaluation {evaluation.id} to stage {stage.value}")
    evaluation.stage = stage
    db.commit()
