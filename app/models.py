import enum

from sqlalchemy import JSON, Boolean, Column, DateTime
from sqlalchemy import Enum as SQLEnum
from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db import Base


class EvaluationStatus(enum.Enum):
    QUEUED = "QUEUED"
    IN_PROGRESS = "IN_PROGRESS"
    FAILED = "FAILED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    MANUAL_REVIEW = "MANUAL_REVIEW"


class EvaluationStage(enum.Enum):
    IDENTITY_RESOLUTION = "IDENTITY_RESOLUTION"
    DATA_COLLECTION = "DATA_COLLECTION"
    SIGNAL_EXTRACTION = "SIGNAL_EXTRACTION"
    SCORING = "SCORING"
    DECISION = "DECISION"


class ProfileEvaluation(Base):
    __tablename__ = "profile_evaluations"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    github_url = Column(String(500), nullable=True)
    website_url = Column(String(500), nullable=True)
    twitter_url = Column(String(500), nullable=True)

    signals = Column(JSON, nullable=False)
    scrape_failures = Column(JSON, nullable=False, default=list)
    score = Column(Integer, nullable=False)
    deterministic_score = Column(Integer, nullable=False)
    llm_score_adjustment = Column(Integer, nullable=False, default=0)
    decision = Column(String(20), nullable=False)
    reasoning = Column(Text, nullable=False)

    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ScraperScript(Base):
    __tablename__ = "scraper_scripts"

    id = Column(Integer, primary_key=True, index=True)
    source = Column(String(30), nullable=False, index=True)
    name = Column(String(120), nullable=False)
    script_code = Column(Text, nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)

    success_count = Column(Integer, nullable=False, default=0)
    failure_count = Column(Integer, nullable=False, default=0)
    last_error = Column(Text, nullable=True)
    last_status = Column(String(20), nullable=True)

    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class ScraperExecutionLog(Base):
    __tablename__ = "scraper_execution_logs"

    id = Column(Integer, primary_key=True, index=True)
    source = Column(String(30), nullable=False, index=True)
    url = Column(String(500), nullable=False)
    script_id = Column(Integer, ForeignKey("scraper_scripts.id"), nullable=True)
    script_name = Column(String(120), nullable=True)
    script_code = Column(Text, nullable=False)
    success = Column(Boolean, nullable=False)
    error = Column(Text, nullable=True)

    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ProfileIntelligenceReport(Base):
    __tablename__ = "profile_intelligence_reports"

    id = Column(Integer, primary_key=True, index=True)
    query_input = Column(String(300), nullable=False)
    name = Column(String(200), nullable=True)
    linkedin_url = Column(String(500), nullable=True)
    qualifiers = Column(JSON, nullable=False, default=list)

    status = Column(String(30), nullable=False)
    disambiguated = Column(Boolean, nullable=False, default=False)
    clarification_questions = Column(JSON, nullable=False, default=list)
    candidates = Column(JSON, nullable=False, default=list)
    sources = Column(JSON, nullable=False, default=list)
    summary = Column(Text, nullable=False, default="")

    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ProfileResolutionReport(Base):
    __tablename__ = "profile_resolution_reports"

    id = Column(Integer, primary_key=True, index=True)
    input_payload = Column(JSON, nullable=False)

    resolved_name = Column(String(200), nullable=True)
    resolved_company = Column(String(200), nullable=True)
    resolved_designation = Column(String(200), nullable=True)
    resolved_location = Column(String(200), nullable=True)
    resolved_confidence = Column(Float, nullable=False, default=0.0)

    ambiguity_flag = Column(Boolean, nullable=False, default=False)
    clarification_question = Column(Text, nullable=True)
    sources = Column(JSON, nullable=False, default=list)
    aggregated_summary = Column(Text, nullable=False, default="")

    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Person(Base):
    __tablename__ = "persons"

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String(200), nullable=True)
    linkedin_url = Column(String(500), nullable=True, unique=True)
    github_url = Column(String(500), nullable=True)
    twitter_url = Column(String(500), nullable=True)
    current_company = Column(String(200), nullable=True)
    current_role = Column(String(200), nullable=True)
    metadata_json = Column(JSON, nullable=True, default=dict)

    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    evaluations = relationship("Evaluation", back_populates="person")


class Evaluation(Base):
    __tablename__ = "evaluations"

    id = Column(Integer, primary_key=True, index=True)
    person_id = Column(Integer, ForeignKey("persons.id"), nullable=False)
    status = Column(
        SQLEnum(EvaluationStatus), nullable=False, default=EvaluationStatus.QUEUED
    )
    stage = Column(SQLEnum(EvaluationStage), nullable=True)
    final_score = Column(Float, nullable=True)
    decision = Column(String(50), nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    person = relationship("Person", back_populates="evaluations")
    signals = relationship("Signal", back_populates="evaluation", uselist=False)


class Signal(Base):
    __tablename__ = "signals"

    id = Column(Integer, primary_key=True, index=True)
    evaluation_id = Column(
        Integer, ForeignKey("evaluations.id"), nullable=False, unique=True
    )
    execution_score = Column(Float, nullable=True)
    technical_depth_score = Column(Float, nullable=True)
    influence_score = Column(Float, nullable=True)
    recognition_score = Column(Float, nullable=True)
    raw_features_json = Column(JSON, nullable=True, default=dict)

    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    evaluation = relationship("Evaluation", back_populates="signals")


class ScoringConfig(Base):
    __tablename__ = "scoring_config"

    id = Column(Integer, primary_key=True, index=True)
    version = Column(String(50), nullable=False, unique=True)
    weights_json = Column(JSON, nullable=False)
    thresholds_json = Column(JSON, nullable=False)
    is_active = Column(Boolean, nullable=False, default=False)

    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
