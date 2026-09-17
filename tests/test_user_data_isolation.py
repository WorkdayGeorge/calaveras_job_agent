from datetime import datetime, timezone

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from job_agent.models import (
    ApplicationPackage,
    Base,
    Evaluation,
    Job,
    Notification,
    ResumeAsset,
    User,
    UserJobState,
)
from job_agent.user_data import assign_legacy_records_to_admin, get_or_create_job_state
from web.auth import hash_password


def make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def add_user(session, email, role="user"):
    now = datetime.now(timezone.utc)
    user = User(
        email=email,
        display_name=email.split("@", 1)[0],
        password_hash=hash_password("a-secure-temporary-password"),
        role=role,
        status="active",
        must_change_password=False,
        created_at=now,
        updated_at=now,
    )
    session.add(user)
    session.commit()
    return user


def add_job(session, status="interested"):
    now = datetime.now(timezone.utc)
    job = Job(
        title="Accounting Technician",
        company="Example Agency",
        apply_url="https://example.com/job",
        first_seen_at=now,
        last_seen_at=now,
        job_fingerprint="a" * 64,
        status=status,
        is_local=True,
        freshness_status="verified_fresh",
    )
    session.add(job)
    session.commit()
    return job


def test_user_job_statuses_are_independent():
    session = make_session()
    first = add_user(session, "first@example.com")
    second = add_user(session, "second@example.com")
    job = add_job(session)

    first_state = get_or_create_job_state(session, first.id, job)
    second_state = get_or_create_job_state(session, second.id, job)
    first_state.status = "applied"
    second_state.status = "ignore"
    session.commit()

    assert first_state.id != second_state.id
    assert first_state.status == "applied"
    assert second_state.status == "ignore"


def test_legacy_records_are_assigned_to_admin_idempotently():
    session = make_session()
    admin = add_user(session, "admin@example.com", role="administrator")
    job = add_job(session, status="applied")
    now = datetime.now(timezone.utc)
    evaluation = Evaluation(
        job_id=job.id,
        resume_version="master-profile-v1",
        fit_score=80,
        classification="Strong Fit",
        recommendation="Apply",
        selected_resume="focused",
        reasoning="Relevant experience",
        evaluated_at=now,
    )
    session.add(evaluation)
    session.commit()
    notification = Notification(
        job_id=job.id,
        evaluation_id=evaluation.id,
        sent_at=now,
        status="sent",
    )
    resume = ResumeAsset(
        resume_type="focused",
        filename="resume.pdf",
        storage_uri="gs://example/resume.pdf",
        uploaded_at=now,
        is_current=True,
    )
    package = ApplicationPackage(
        job_id=job.id,
        version=1,
        tailored_resume="Resume",
        cover_letter="Letter",
        interview_questions=[],
        truth_check_notes=[],
        created_at=now,
        updated_at=now,
    )
    session.add_all([notification, resume, package])
    session.commit()

    assign_legacy_records_to_admin(session, admin)
    assign_legacy_records_to_admin(session, admin)

    assert evaluation.user_id == admin.id
    assert notification.user_id == admin.id
    assert resume.user_id == admin.id
    assert package.user_id == admin.id
    states = session.scalars(
        select(UserJobState).where(
            UserJobState.user_id == admin.id,
            UserJobState.job_id == job.id,
        )
    ).all()
    assert len(states) == 1
    assert states[0].status == "applied"
    assert states[0].applied_at is not None
