from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from job_agent.models import (
    Base,
    CandidateProfile,
    Evaluation,
    Job,
    Notification,
    User,
    UserJobMatch,
    UserPreference,
    UserJobState,
)
from web.app import (
    administrator_job_rows,
    administrator_notification_candidates,
    send_administrator_job_notifications,
)
from web.auth import hash_password


def make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def add_user(session, email, now):
    user = User(
        email=email,
        display_name=email.split("@", 1)[0],
        password_hash=hash_password("a-secure-temporary-password"),
        role="user",
        status="active",
        must_change_password=False,
        created_at=now,
        updated_at=now,
    )
    session.add(user)
    session.flush()
    session.add(CandidateProfile(
        user_id=user.id,
        profile_data={"location": "Avery, CA"},
        resume_version="profile-v2",
        version=2,
        is_active=True,
        created_at=now,
        updated_at=now,
    ))
    session.add(UserPreference(
        user_id=user.id,
        notification_email=f"alerts-{email}",
        immediate_alerts=True,
        daily_digest=True,
        digest_time="17:05",
        created_at=now,
        updated_at=now,
    ))
    return user


def add_evaluation(session, user, job, score, recommendation, now, version="profile-v2"):
    session.add(Evaluation(
        user_id=user.id,
        job_id=job.id,
        resume_version=version,
        fit_score=score,
        classification="Strong Fit" if score >= 75 else "Possible Fit",
        recommendation=recommendation,
        selected_resume="focused",
        reasoning="Relevant",
        evaluated_at=now,
    ))


def test_administrator_job_rows_aggregate_current_user_metrics():
    session = make_session()
    now = datetime.now(timezone.utc)
    first = add_user(session, "first@example.com", now)
    second = add_user(session, "second@example.com", now)
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

    for user in (first, second):
        session.add(UserJobMatch(
            user_id=user.id,
            job_id=job.id,
            search_term="accounting",
            first_matched_at=now,
            last_matched_at=now,
        ))
    # A second matching term must not double-count the same user.
    session.add(UserJobMatch(
        user_id=first.id,
        job_id=job.id,
        search_term="bookkeeping",
        first_matched_at=now,
        last_matched_at=now,
    ))
    add_evaluation(session, first, job, 82, "Apply", now)
    add_evaluation(session, second, job, 68, "Review", now)
    # Historical scores must not be mixed with each user's current profile.
    add_evaluation(session, second, job, 95, "Apply", now, version="profile-v1")
    session.add(UserJobState(
        user_id=first.id,
        job_id=job.id,
        status="applied",
        applied_at=now,
        created_at=now,
        updated_at=now,
    ))
    session.commit()

    row = administrator_job_rows(session)[0]

    assert row[0].id == job.id
    assert row.assigned_users == 2
    assert row.evaluated_users == 2
    assert row.best_fit == 82
    assert float(row.average_fit) == 75.0
    assert row.strong_fits == 1
    assert row.apply_recommendations == 1
    assert row.notified_users == 0
    assert row.applied_users == 1


def test_administrator_notifications_require_review_and_prevent_duplicates():
    session = make_session()
    now = datetime.now(timezone.utc)
    user = add_user(session, "person@example.com", now)
    job = Job(
        title="Bookkeeper",
        company="Example Company",
        apply_url="https://example.com/bookkeeper",
        source="example",
        first_seen_at=now,
        last_seen_at=now,
        job_fingerprint="b" * 64,
        is_local=True,
        freshness_status="verified_fresh",
    )
    session.add(job)
    session.flush()
    session.add(UserJobMatch(
        user_id=user.id,
        job_id=job.id,
        search_term="bookkeeper",
        first_matched_at=now,
        last_matched_at=now,
    ))
    add_evaluation(session, user, job, 88, "Apply", now)
    session.commit()

    deliveries = []

    def fake_sender(job_payload, evaluation_payload, bucket, recipient=None):
        deliveries.append((job_payload, evaluation_payload, bucket, recipient))
        return True, "sent"

    candidates = administrator_notification_candidates(session, job.id)
    assert candidates[0]["recommended"] is True
    assert candidates[0]["previously_notified"] is False
    assert candidates[0]["recipient"] == "alerts-person@example.com"

    first = send_administrator_job_notifications(
        session, job, candidates, {user.id}, sender=fake_sender
    )
    assert first == {"sent": 1, "failed": 0, "skipped": 0}
    assert len(deliveries) == 1
    assert session.query(Notification).count() == 1

    candidates = administrator_notification_candidates(session, job.id)
    assert candidates[0]["previously_notified"] is True
    duplicate = send_administrator_job_notifications(
        session, job, candidates, {user.id}, sender=fake_sender
    )
    assert duplicate == {"sent": 0, "failed": 0, "skipped": 1}
    assert len(deliveries) == 1

    resend = send_administrator_job_notifications(
        session,
        job,
        candidates,
        {user.id},
        allow_resend=True,
        sender=fake_sender,
    )
    assert resend == {"sent": 1, "failed": 0, "skipped": 0}
    assert len(deliveries) == 2
    assert administrator_job_rows(session)[0].notified_users == 1
