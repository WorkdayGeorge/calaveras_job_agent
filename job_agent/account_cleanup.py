from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select, update

from .models import (
    ApplicationAssistantProfile,
    ApplicationPackage,
    AuditEvent,
    AuthToken,
    CandidateProfile,
    Evaluation,
    EvaluationBackfill,
    Notification,
    ResumeAsset,
    User,
    UserJobMatch,
    UserJobState,
    UserOnboarding,
    UserPreference,
    UserSearchTerm,
)


def candidate_data_summary(session, user_id: str) -> dict[str, int]:
    models = {
        "resumes": ResumeAsset,
        "profiles": CandidateProfile,
        "application_packages": ApplicationPackage,
        "evaluations": Evaluation,
        "notifications": Notification,
        "search_terms": UserSearchTerm,
        "job_matches": UserJobMatch,
        "job_states": UserJobState,
    }
    return {
        label: len(session.scalars(select(model).where(model.user_id == user_id)).all())
        for label, model in models.items()
    }


def resume_storage_uris(session, user_id: str) -> list[str]:
    return list(session.scalars(
        select(ResumeAsset.storage_uri).where(ResumeAsset.user_id == user_id)
    ).all())


def reset_candidate_data(session, user: User) -> None:
    user_id = user.id
    session.execute(delete(Notification).where(Notification.user_id == user_id))
    session.execute(delete(ApplicationPackage).where(ApplicationPackage.user_id == user_id))
    session.execute(delete(Evaluation).where(Evaluation.user_id == user_id))
    session.execute(delete(EvaluationBackfill).where(EvaluationBackfill.user_id == user_id))
    session.execute(delete(UserJobState).where(UserJobState.user_id == user_id))
    session.execute(delete(UserJobMatch).where(UserJobMatch.user_id == user_id))
    session.execute(delete(UserSearchTerm).where(UserSearchTerm.user_id == user_id))
    session.execute(delete(ApplicationAssistantProfile).where(
        ApplicationAssistantProfile.user_id == user_id
    ))
    session.execute(delete(CandidateProfile).where(CandidateProfile.user_id == user_id))
    session.execute(delete(ResumeAsset).where(ResumeAsset.user_id == user_id))

    now = datetime.now(timezone.utc)
    onboarding = session.get(UserOnboarding, user_id)
    if not onboarding:
        onboarding = UserOnboarding(
            user_id=user_id,
            invited_at=now,
            invitation_expires_at=now + timedelta(hours=48),
            password_set_at=now,
            email_verified_at=now,
            updated_at=now,
        )
        session.add(onboarding)
    else:
        onboarding.password_set_at = now
        onboarding.email_verified_at = now
        onboarding.completed_at = None
        onboarding.updated_at = now
    user.status = "onboarding"
    user.updated_at = now
    session.commit()


def delete_user_account(session, user: User) -> None:
    user_id = user.id
    reset_candidate_data(session, user)
    session.execute(update(AuditEvent).where(
        AuditEvent.actor_user_id == user_id
    ).values(actor_user_id=None))
    session.execute(update(AuditEvent).where(
        AuditEvent.target_user_id == user_id
    ).values(target_user_id=None))
    session.execute(delete(AuthToken).where(AuthToken.user_id == user_id))
    session.execute(delete(UserOnboarding).where(UserOnboarding.user_id == user_id))
    session.execute(delete(UserPreference).where(UserPreference.user_id == user_id))
    session.delete(user)
    session.commit()
