from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from .models import AppSetting, Job, SearchTerm, User, UserJobMatch, UserSearchTerm


def normalize_search_term(value: str) -> str:
    return " ".join(str(value or "").split()).strip()


def ensure_user_search_terms(session, user: User) -> list[UserSearchTerm]:
    marker_key = f"user_search_terms_initialized:{user.id}"
    terms = session.scalars(
        select(UserSearchTerm)
        .where(UserSearchTerm.user_id == user.id)
        .order_by(UserSearchTerm.term)
    ).all()
    if session.get(AppSetting, marker_key):
        return terms
    now = datetime.now(timezone.utc)
    if terms:
        session.add(AppSetting(key=marker_key, value="complete", updated_at=now))
        session.commit()
        return terms
    defaults = session.scalars(
        select(SearchTerm).where(SearchTerm.enabled.is_(True)).order_by(SearchTerm.term)
    ).all()
    for default in defaults:
        session.add(UserSearchTerm(
            user_id=user.id,
            term=default.term,
            enabled=True,
            created_at=now,
        ))
    session.add(AppSetting(key=marker_key, value="complete", updated_at=now))
    session.commit()
    return session.scalars(
        select(UserSearchTerm)
        .where(UserSearchTerm.user_id == user.id)
        .order_by(UserSearchTerm.term)
    ).all()


def enabled_user_terms(session, user_id: str) -> list[str]:
    return session.scalars(
        select(UserSearchTerm.term)
        .where(
            UserSearchTerm.user_id == user_id,
            UserSearchTerm.enabled.is_(True),
        )
        .order_by(UserSearchTerm.term)
    ).all()


def record_user_job_match(session, user_id: str, job_id: str, search_term: str) -> None:
    term = normalize_search_term(search_term) or "matched"
    now = datetime.now(timezone.utc)
    match = session.scalar(
        select(UserJobMatch).where(
            UserJobMatch.user_id == user_id,
            UserJobMatch.job_id == job_id,
            UserJobMatch.search_term == term,
        )
    )
    if match:
        match.last_matched_at = now
    else:
        session.add(UserJobMatch(
            user_id=user_id,
            job_id=job_id,
            search_term=term,
            first_matched_at=now,
            last_matched_at=now,
        ))
    try:
        session.flush()
    except IntegrityError:
        session.rollback()


def seed_legacy_job_matches(session) -> int:
    """One-time migration preserving existing users' access to existing jobs."""
    marker_key = "user_job_match_migration_v1"
    if session.get(AppSetting, marker_key):
        return 0
    users = session.scalars(select(User).where(User.status != "archived")).all()
    jobs = session.scalars(select(Job).where(Job.is_local.is_(True))).all()
    existing = set(session.execute(
        select(UserJobMatch.user_id, UserJobMatch.job_id).where(
            UserJobMatch.search_term == "legacy-migration"
        )
    ).all())
    now = datetime.now(timezone.utc)
    created = 0
    for user in users:
        ensure_user_search_terms(session, user)
        for job in jobs:
            if (user.id, job.id) in existing:
                continue
            session.add(UserJobMatch(
                user_id=user.id,
                job_id=job.id,
                search_term="legacy-migration",
                first_matched_at=now,
                last_matched_at=now,
            ))
            created += 1
    session.add(AppSetting(key=marker_key, value="complete", updated_at=now))
    session.commit()
    return created
