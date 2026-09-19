from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import exists, func, select

from .models import CandidateProfile, Evaluation, EvaluationBackfill, Job


def backfill_progress(session, user_id: str, resume_version: str) -> dict:
    total = session.scalar(
        select(func.count(Job.id)).where(Job.is_local.is_(True))
    ) or 0
    completed = session.scalar(
        select(func.count(Evaluation.id))
        .join(Job, Evaluation.job_id == Job.id)
        .where(
            Evaluation.user_id == user_id,
            Evaluation.resume_version == resume_version,
            Job.is_local.is_(True),
        )
    ) or 0
    request = session.scalar(
        select(EvaluationBackfill).where(
            EvaluationBackfill.user_id == user_id,
            EvaluationBackfill.resume_version == resume_version,
        )
    )
    return {
        "total": total,
        "completed": min(completed, total),
        "pending": max(0, total - completed),
        "request": request,
    }


def request_backfill(session, user_id: str) -> EvaluationBackfill:
    profile = session.get(CandidateProfile, user_id)
    if not profile:
        raise ValueError("Candidate profile not found.")
    progress = backfill_progress(session, user_id, profile.resume_version)
    request = progress["request"]
    now = datetime.now(timezone.utc)
    if not request:
        request = EvaluationBackfill(
            user_id=user_id,
            resume_version=profile.resume_version,
            created_at=now,
            updated_at=now,
        )
        session.add(request)
    request.status = "queued" if progress["pending"] else "complete"
    request.total_jobs = progress["total"]
    request.completed_jobs = progress["completed"]
    request.failed_jobs = 0
    request.updated_at = now
    request.completed_at = now if request.status == "complete" else None
    session.commit()
    session.refresh(request)
    return request


def queued_backfills(session):
    return session.scalars(
        select(EvaluationBackfill)
        .where(EvaluationBackfill.status.in_(("queued", "running")))
        .order_by(EvaluationBackfill.created_at)
    ).all()


def pending_backfill_jobs(session, request: EvaluationBackfill, limit: int):
    already_scored = exists(
        select(Evaluation.id).where(
            Evaluation.job_id == Job.id,
            Evaluation.user_id == request.user_id,
            Evaluation.resume_version == request.resume_version,
        )
    )
    return session.scalars(
        select(Job)
        .where(Job.is_local.is_(True), ~already_scored)
        .order_by(Job.posted_at.desc().nullslast(), Job.first_seen_at.desc())
        .limit(limit)
    ).all()


def refresh_backfill(session, request: EvaluationBackfill) -> None:
    progress = backfill_progress(session, request.user_id, request.resume_version)
    request.total_jobs = progress["total"]
    request.completed_jobs = progress["completed"]
    request.updated_at = datetime.now(timezone.utc)
    if progress["pending"] == 0:
        request.status = "complete"
        request.completed_at = request.updated_at
    else:
        request.status = "running"
    session.commit()
