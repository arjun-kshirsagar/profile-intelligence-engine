from sqlalchemy import JSON, Column, DateTime, Integer, String, Text
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
    score = Column(Integer, nullable=False)
    deterministic_score = Column(Integer, nullable=False)
    llm_score_adjustment = Column(Integer, nullable=False, default=0)
    decision = Column(String(20), nullable=False)
    reasoning = Column(Text, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
