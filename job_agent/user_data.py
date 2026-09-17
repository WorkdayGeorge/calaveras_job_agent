from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select, update

from .models import (
    ApplicationPackage,
    Evaluation,
    Job,
    Notification,
    ResumeAsset,
    User,
    UserJobState,
)


def assign_legacy_records_to_admin(session, admin: User | None) -> None:
    """Idempotently assign pre-multi-user records to the administrator."""
    if not admin:
        return

    for model in (Evaluation, Notification, ResumeAsset, ApplicationPackage):
        session.execute(
            update(model).where(model.user_id.is_(None)).values(user_id=admin.id)
        )
    session.execute(
        update(ApplicationPackage)
        .where(
            ApplicationPackage.user_id == admin.id,
            ApplicationPackage.candidate_profile_version.is_(None),
        )
        .values(candidate_profile_version="master-profile-v1")
    )

    existing_job_ids = set(
        session.scalars(
            select(UserJobState.job_id).where(UserJobState.user_id == admin.id)
        ).all()
    )
    now = datetime.now(timezone.utc)
    for job in session.scalars(select(Job)).all():
        if job.id not in existing_job_ids:
            session.add(UserJobState(
                user_id=admin.id,
                job_id=job.id,
                status=job.status or "new",
                application_url=job.apply_url,
                created_at=now,
                updated_at=now,
                applied_at=now if job.status == "applied" else None,
            ))
    session.commit()
    session.expire_all()


def get_or_create_job_state(session, user_id: str, job: Job) -> UserJobState:
    state = session.scalar(
        select(UserJobState).where(
            UserJobState.user_id == user_id,
            UserJobState.job_id == job.id,
        )
    )
    if state:
        return state

    now = datetime.now(timezone.utc)
    state = UserJobState(
        user_id=user_id,
        job_id=job.id,
        status="new",
        application_url=job.apply_url,
        created_at=now,
        updated_at=now,
    )
    session.add(state)
    session.flush()
    return state
