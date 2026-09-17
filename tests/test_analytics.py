from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from job_agent.analytics import build_admin_analytics, resolve_date_range
from job_agent.models import Base, Evaluation, Job, Notification, User, UserJobState
from web.auth import hash_password


def make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def test_date_ranges_use_pacific_calendar_boundaries():
    now = datetime(2026, 9, 17, 20, 0, tzinfo=timezone.utc)
    start, end, label = resolve_date_range("7d", now=now)
    assert label == "Last 7 days"
    assert start.astimezone().tzinfo is not None
    assert (end - start).days == 7


def test_analytics_counts_and_drilldowns_are_user_attributed():
    session = make_session()
    now = datetime.now(timezone.utc)
    user = User(
        email="person@example.com",
        display_name="Example Person",
        password_hash=hash_password("a-secure-temporary-password"),
        role="user",
        status="active",
        must_change_password=False,
        created_at=now,
        updated_at=now,
    )
    session.add(user)
    session.flush()
    job = Job(
        title="Accounting Technician",
        company="Example Agency",
        apply_url="https://example.com/job",
        source="example",
        first_seen_at=now,
        last_seen_at=now,
        job_fingerprint="a" * 64,
        is_local=True,
        freshness_status="verified_fresh",
    )
    session.add(job)
    session.flush()
    evaluation = Evaluation(
        user_id=user.id,
        job_id=job.id,
        resume_version="profile-v1",
        fit_score=82,
        classification="Strong Fit",
        recommendation="Apply",
        selected_resume="focused",
        reasoning="Relevant",
        evaluated_at=now,
    )
    session.add(evaluation)
    session.flush()
    session.add(Notification(
        user_id=user.id,
        job_id=job.id,
        evaluation_id=evaluation.id,
        channel="email",
        sent_at=now,
        status="sent",
    ))
    session.add(UserJobState(
        user_id=user.id,
        job_id=job.id,
        status="interview",
        applied_at=now,
        interview_at=now,
        application_url=job.apply_url,
        created_at=now,
        updated_at=now,
    ))
    session.commit()

    analytics = build_admin_analytics(
        session,
        now.replace(hour=0, minute=0, second=0, microsecond=0),
        now.replace(hour=0, minute=0, second=0, microsecond=0)
        + timedelta(days=1),
    )
    assert analytics["metrics"]["notifications_sent"] == 1
    assert analytics["metrics"]["applications"] == 1
    assert analytics["metrics"]["interviews"] == 1
    assert analytics["notifications"][0]["user"].id == user.id
    assert analytics["applications"][0]["job"].title == "Accounting Technician"
    assert analytics["sources"][0]["applied"] == 1
