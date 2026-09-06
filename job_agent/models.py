\
from __future__ import annotations

import uuid
from datetime import datetime
from sqlalchemy import (
    String, Text, Integer, DateTime, ForeignKey, Boolean, UniqueConstraint
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import JSON

class Base(DeclarativeBase):
    pass

def uuid_str() -> str:
    return str(uuid.uuid4())

class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    provider_job_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    company: Mapped[str] = mapped_column(Text, nullable=False)
    location: Mapped[str | None] = mapped_column(Text)
    employment_type: Mapped[str | None] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text)
    requirements: Mapped[list] = mapped_column(JSON, default=list)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    posted_time_confidence: Mapped[str] = mapped_column(String(50), default="unverified")
    apply_url: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str | None] = mapped_column(String(100))
    source_url: Mapped[str | None] = mapped_column(Text)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    job_fingerprint: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="new")
    is_local: Mapped[bool] = mapped_column(Boolean, default=False)
    freshness_status: Mapped[str] = mapped_column(String(50), default="unverified")

class Resume(Base):
    __tablename__ = "resumes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    resume_text: Mapped[str] = mapped_column(Text, nullable=False)
    skills: Mapped[dict] = mapped_column(JSON, default=dict)
    experience: Mapped[list] = mapped_column(JSON, default=list)
    education: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)

class Evaluation(Base):
    __tablename__ = "evaluations"
    __table_args__ = (UniqueConstraint("job_id", "resume_version", name="uq_job_resume_version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), nullable=False)
    resume_version: Mapped[str] = mapped_column(String(50), nullable=False)
    fit_score: Mapped[int] = mapped_column(Integer, nullable=False)
    classification: Mapped[str] = mapped_column(String(50), nullable=False)
    recommendation: Mapped[str] = mapped_column(String(50), nullable=False)
    selected_resume: Mapped[str] = mapped_column(String(50), nullable=False)
    matching_skills: Mapped[list] = mapped_column(JSON, default=list)
    transferable_skills: Mapped[list] = mapped_column(JSON, default=list)
    missing_requirements: Mapped[list] = mapped_column(JSON, default=list)
    uncertain_requirements: Mapped[list] = mapped_column(JSON, default=list)
    reasoning: Mapped[str] = mapped_column(Text, nullable=False)
    score_breakdown: Mapped[dict] = mapped_column(JSON, default=dict)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), nullable=False)
    evaluation_id: Mapped[str] = mapped_column(ForeignKey("evaluations.id"), nullable=False)
    channel: Mapped[str] = mapped_column(String(50), default="console")
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(30), default="sent")
