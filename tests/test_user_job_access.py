from datetime import datetime, timezone
from types import SimpleNamespace

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from job_agent.models import Base, Job, User, UserJobMatch
from web.app import get_assigned_job, job_search_clause
from web.auth import hash_password


def test_user_cannot_open_an_unassigned_job():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    now = datetime.now(timezone.utc)
    user = User(
        email="assigned@example.com", display_name="Assigned User",
        password_hash=hash_password("temporary-passphrase"), role="user",
        status="active", must_change_password=False,
        created_at=now, updated_at=now,
    )
    session.add(user)
    session.flush()
    jobs = []
    for index in range(2):
        job = Job(
            title=f"Job {index}", company="Example", location="Arnold, CA",
            apply_url=f"https://example.com/{index}", source="test",
            first_seen_at=now, last_seen_at=now,
            job_fingerprint=str(index).zfill(64), is_local=True,
            freshness_status="verified_fresh",
        )
        session.add(job)
        jobs.append(job)
    session.flush()
    session.add(UserJobMatch(
        user_id=user.id, job_id=jobs[0].id, search_term="accounting",
        first_matched_at=now, last_matched_at=now,
    ))
    session.commit()
    request = SimpleNamespace(session={"user_id": user.id})

    assert get_assigned_job(session, jobs[0].id, request).id == jobs[0].id
    assert get_assigned_job(session, jobs[1].id, request) is None


def test_job_search_matches_title_company_and_location_case_insensitively():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    now = datetime.now(timezone.utc)
    jobs = [
        Job(
            title="Accounting Technician", company="County Office",
            location="San Andreas, CA", apply_url="https://example.com/1",
            source="test", first_seen_at=now, last_seen_at=now,
            job_fingerprint="1" * 64, is_local=True,
            freshness_status="verified_fresh",
        ),
        Job(
            title="Service Representative", company="Mountain Utilities",
            location="Arnold, CA", apply_url="https://example.com/2",
            source="test", first_seen_at=now, last_seen_at=now,
            job_fingerprint="2" * 64, is_local=True,
            freshness_status="verified_fresh",
        ),
    ]
    session.add_all(jobs)
    session.commit()

    for query, expected_title in [
        ("accounting", "Accounting Technician"),
        ("MOUNTAIN", "Service Representative"),
        ("arnold", "Service Representative"),
    ]:
        matches = session.scalars(
            select(Job).where(job_search_clause(query))
        ).all()
        assert [job.title for job in matches] == [expected_title]


def test_empty_job_search_adds_no_filter():
    assert job_search_clause("   ") is None
