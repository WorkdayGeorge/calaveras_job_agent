\
from __future__ import annotations

from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Job, Evaluation
from .schemas import NormalizedJob

def upsert_job(session: Session, item: NormalizedJob) -> tuple[Job, bool]:
    existing = session.scalar(select(Job).where(Job.job_fingerprint == item.job_fingerprint))
    now = datetime.now(timezone.utc)

    if existing:
        existing.last_seen_at = now
        existing.posted_at = item.posted_at or existing.posted_at
        existing.freshness_status = item.freshness_status
        existing.posted_time_confidence = item.posted_time_confidence
        existing.is_local = item.is_local
        session.commit()
        return existing, False

    job = Job(
        provider_job_id=item.provider_job_id,
        title=item.title,
        company=item.company,
        location=item.location,
        employment_type=item.employment_type,
        description=item.description,
        requirements=item.requirements,
        posted_at=item.posted_at,
        posted_time_confidence=item.posted_time_confidence,
        apply_url=item.apply_url,
        source=item.source,
        source_url=item.source_url,
        first_seen_at=now,
        last_seen_at=now,
        job_fingerprint=item.job_fingerprint,
        is_local=item.is_local,
        freshness_status=item.freshness_status,
        status="new",
    )
    session.add(job)
    session.commit()
    session.refresh(job)
    return job, True

def evaluation_exists(session: Session, job_id: str, resume_version: str) -> bool:
    return session.scalar(
        select(Evaluation.id).where(
            Evaluation.job_id == job_id,
            Evaluation.resume_version == resume_version
        )
    ) is not None
