import asyncio
from datetime import datetime

from sqlalchemy.orm import Session

from app.agents.explanation import ExplanationAgent
from app.agents.identity import IdentityResolutionAgent
from app.celery_app import celery_app
from app.collectors.github_collector import GitHubCollector
from app.collectors.linkedin_collector import LinkedInCollector
from app.collectors.web_search_collector import WebSearchCollector
from app.db import SessionLocal
from app.logger import logger
from app.models import Evaluation, EvaluationStage, EvaluationStatus, Signal
from app.scoring_engine import ScoringEngine
from app.signal_extractor import SignalExtractor


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

        # We need an event loop for the async agents
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            # Mock search results for identity resolution
            mock_search_results = [
                {
                    "title": f"{person.full_name} | LinkedIn",
                    "snippet": f"{person.current_role} at {person.current_company}",
                },
                {
                    "title": f"{person.full_name} - GitHub",
                    "link": "https://github.com/johndoe",
                    "snippet": "Building distributed systems.",
                },
                {
                    "title": f"{person.full_name} (@johndoe) / X",
                    "link": "https://twitter.com/johndoe",
                    "snippet": "Thoughts on AI and backend engineering.",
                },
            ]

            identity_agent = IdentityResolutionAgent()
            identity_result = loop.run_until_complete(
                identity_agent.resolve(
                    name=person.full_name or "Unknown",
                    company=person.current_company,
                    role=person.current_role,
                    search_results=mock_search_results,
                )
            )

            if identity_result.github_url and not person.github_url:
                person.github_url = identity_result.github_url
            if identity_result.twitter_url and not person.twitter_url:
                person.twitter_url = identity_result.twitter_url

            db.commit()

            # Phase 2: Data Collection
            _update_stage(db, evaluation, EvaluationStage.DATA_COLLECTION)

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

        extractor = SignalExtractor()
        extracted_signals = extractor.extract(person.metadata_json)

        # Store signals in DB
        signal_row = (
            db.query(Signal).filter(Signal.evaluation_id == evaluation.id).first()
        )
        if not signal_row:
            signal_row = Signal(evaluation_id=evaluation.id)
            db.add(signal_row)

        signal_row.execution_score = extracted_signals.execution_score
        signal_row.technical_depth_score = extracted_signals.technical_depth_score
        signal_row.influence_score = extracted_signals.influence_score
        signal_row.recognition_score = extracted_signals.recognition_score
        signal_row.raw_features_json = extracted_signals.raw_features
        db.commit()

        # Phase 4: Scoring
        _update_stage(db, evaluation, EvaluationStage.SCORING)

        scoring_engine = ScoringEngine(db)
        final_score, decision, scoring_version = scoring_engine.compute_and_decide(
            signal_row
        )

        evaluation.final_score = final_score
        db.commit()

        # Phase 5: Decision & Explanation
        _update_stage(db, evaluation, EvaluationStage.DECISION)

        evaluation.decision = decision

        # Generate Human-Readable Explanation
        try:
            explanation_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(explanation_loop)

            explanation_agent = ExplanationAgent()
            explanation_result = explanation_loop.run_until_complete(
                explanation_agent.generate_explanation(
                    name=person.full_name or "Candidate",
                    final_score=final_score,
                    decision=decision,
                    execution_score=signal_row.execution_score or 0.0,
                    technical_depth_score=signal_row.technical_depth_score or 0.0,
                    influence_score=signal_row.influence_score or 0.0,
                    recognition_score=signal_row.recognition_score or 0.0,
                    raw_features=signal_row.raw_features_json or {},
                )
            )

            evaluation.summary = explanation_result.summary
            evaluation.strengths = explanation_result.strengths
            evaluation.weaknesses = explanation_result.weaknesses

            explanation_loop.close()
        except Exception as explanation_exc:
            logger.error(f"Failed to generate explanation: {explanation_exc}")
            evaluation.summary = (
                "Evaluation completed, but explanation generation failed."
            )

        # If score is between thresholds, explicitly mark as MANUAL_REVIEW
        if decision == "MANUAL_REVIEW":
            evaluation.status = EvaluationStatus.MANUAL_REVIEW
        else:
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
