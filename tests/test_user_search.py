from datetime import datetime, timezone

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from job_agent.models import Base, Job, SearchTerm, User, UserJobMatch
from job_agent.user_search import (
    enabled_user_terms,
    ensure_user_search_terms,
    record_user_job_match,
    seed_legacy_job_matches,
)
from web.auth import hash_password
from job_agent.pipeline import targets_for_search_term


def make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def make_user(session, email="user@example.com"):
    now = datetime.now(timezone.utc)
    user = User(
        email=email, display_name="Example User",
        password_hash=hash_password("temporary-passphrase"),
        role="user", status="active", must_change_password=False,
        created_at=now, updated_at=now,
    )
    session.add(user)
    session.commit()
    return user


def test_new_user_receives_copies_of_enabled_default_terms():
    session = make_session()
    now = datetime.now(timezone.utc)
    session.add_all([
        SearchTerm(term="Accounting Clerk", enabled=True, created_at=now),
        SearchTerm(term="Disabled Default", enabled=False, created_at=now),
    ])
    user = make_user(session)
    terms = ensure_user_search_terms(session, user)
    assert [term.term for term in terms] == ["Accounting Clerk"]
    assert enabled_user_terms(session, user.id) == ["Accounting Clerk"]
    for term in terms:
        session.delete(term)
    session.commit()
    assert ensure_user_search_terms(session, user) == []


def test_job_matches_are_idempotent_and_user_specific():
    session = make_session()
    user = make_user(session)
    other = make_user(session, "other@example.com")
    now = datetime.now(timezone.utc)
    job = Job(
        title="Accounting Clerk", company="Example", location="Arnold, CA",
        apply_url="https://example.com/job", source="test",
        first_seen_at=now, last_seen_at=now, job_fingerprint="x" * 64,
        is_local=True, freshness_status="verified_fresh",
    )
    session.add(job)
    session.commit()
    record_user_job_match(session, user.id, job.id, "accounting clerk")
    record_user_job_match(session, user.id, job.id, "accounting clerk")
    assert session.scalar(select(func.count(UserJobMatch.id))) == 1
    assert session.scalar(select(UserJobMatch.user_id)) == user.id
    assert user.id != other.id


def test_legacy_migration_preserves_existing_job_access_once():
    session = make_session()
    user = make_user(session)
    now = datetime.now(timezone.utc)
    job = Job(
        title="Legacy Job", company="Example", location="Arnold, CA",
        apply_url="https://example.com/legacy", source="legacy",
        first_seen_at=now, last_seen_at=now, job_fingerprint="l" * 64,
        is_local=True, freshness_status="unverified",
    )
    session.add(job)
    session.commit()
    assert seed_legacy_job_matches(session) == 1
    assert seed_legacy_job_matches(session) == 0
    match = session.scalar(select(UserJobMatch))
    assert match.user_id == user.id
    assert match.job_id == job.id


def test_search_term_routes_jobs_only_to_subscribed_users():
    targets = [
        {"user_id": "accounting", "search_terms": ["Accounting Clerk"]},
        {"user_id": "warehouse", "search_terms": ["Warehouse Coordinator"]},
    ]
    routed = targets_for_search_term(targets, "accounting clerk")
    assert [target["user_id"] for target in routed] == ["accounting"]
