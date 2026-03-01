from sqlalchemy import JSON, Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.sql import func

from app.db import Base


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

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


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

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
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

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


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

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
