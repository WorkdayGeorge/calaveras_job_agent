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
    detail: Mapped[str | None] = mapped_column(Text)

class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

class SearchTerm(Base):
    __tablename__ = "search_terms"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    term: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

class RunLog(Base):
    __tablename__ = "run_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(30), default="running")
    provider: Mapped[str | None] = mapped_column(String(100))
    found: Mapped[int] = mapped_column(Integer, default=0)
    new_local_jobs: Mapped[int] = mapped_column(Integer, default=0)
    evaluated: Mapped[int] = mapped_column(Integer, default=0)
    alerts: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)

class ResumeAsset(Base):
    __tablename__ = "resume_assets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    resume_type: Mapped[str] = mapped_column(String(50), nullable=False)  # focused | all-work-experience
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_uri: Mapped[str] = mapped_column(Text, nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)

class ApplicationPackage(Base):
    __tablename__ = "application_packages"
    __table_args__ = (
        UniqueConstraint(
            "job_id",
            "version",
            name="uq_application_package_job_version",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=uuid_str,
    )
    job_id: Mapped[str] = mapped_column(
        ForeignKey("jobs.id"),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
    )

    tailored_resume: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    cover_letter: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    interview_questions: Mapped[list] = mapped_column(
        JSON,
        default=list,
    )

    job_description_snapshot: Mapped[str | None] = mapped_column(Text)
    generation_model: Mapped[str | None] = mapped_column(String(100))
    truth_check_notes: Mapped[list] = mapped_column(
        JSON,
        default=list,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )


