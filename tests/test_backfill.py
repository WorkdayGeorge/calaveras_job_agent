from datetime import datetime, timezone
from types import SimpleNamespace

from sqlalchemy import create_engine, func, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import sessionmaker

from job_agent.backfill import (
    backfill_progress,
    pending_backfill_jobs,
    refresh_backfill,
    request_backfill,
)
from job_agent.models import (
    Base,
    CandidateProfile,
    Evaluation,
    Job,
    Notification,
    User,
    UserJobMatch,
)
from job_agent.pipeline import evaluate_for_target
from web.auth import hash_password


def make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def seed_profile_and_jobs(session, count=3):
    now = datetime.now(timezone.utc)
    user = User(
        email="backfill@example.com", display_name="Backfill User",
        password_hash=hash_password("temporary-passphrase"), role="user",
        status="active", must_change_password=False,
        created_at=now, updated_at=now,
    )
    session.add(user)
    session.flush()
    profile_data = {
        "name": "Backfill User", "location": "Arnold, CA",
        "career_targets": [],
        "skills": {"accounting_office": [], "data_technical": [], "operations": [], "transferable": []},
        "experience": [], "education_training": [],
        "resume_selection_rules": {"focused": [], "all_work_experience": []},
        "truth_constraints": [],
    }
    session.add(CandidateProfile(
        user_id=user.id, profile_data=profile_data, resume_version="profile-v1",
        version=1, is_active=True, created_at=now, updated_at=now,
    ))
    jobs = []
    for index in range(count):
        job = Job(
            title=f"Job {index}", company="Example", location="Arnold, CA",
            apply_url=f"https://example.com/{index}", source="test",
            first_seen_at=now, last_seen_at=now,
            job_fingerprint=str(index).zfill(64), is_local=True,
            freshness_status="verified_fresh",
        )
        session.add(job)
        session.flush()
        session.add(UserJobMatch(
            user_id=user.id, job_id=job.id, search_term="test",
            first_matched_at=now, last_matched_at=now,
        ))
        jobs.append(job)
    session.commit()
    return user, profile_data, jobs


def test_backfill_is_resumable_and_reports_progress():
    session = make_session()
    user, _, jobs = seed_profile_and_jobs(session)
    request = request_backfill(session, user.id)
    assert request.status == "queued"
    assert request.total_jobs == 3
    assert len(pending_backfill_jobs(session, request, limit=2)) == 2

    now = datetime.now(timezone.utc)
    session.add(Evaluation(
        user_id=user.id, job_id=jobs[0].id, resume_version="profile-v1",
        fit_score=50, classification="Poor Fit", recommendation="Skip",
        selected_resume="focused", reasoning="Test", evaluated_at=now,
    ))
    session.commit()
    refresh_backfill(session, request)
    progress = backfill_progress(session, user.id, "profile-v1")
    assert progress["completed"] == 1
    assert progress["pending"] == 2
    assert request.status == "running"


def test_historical_backfill_never_creates_notifications(monkeypatch):
    session = make_session()
    user, profile, jobs = seed_profile_and_jobs(session, count=1)
    result = {
        "fit_score": 99, "classification": "Strong Fit",
        "recommendation": "Apply", "selected_resume": "focused",
        "reasoning": "Test",
    }
    monkeypatch.setattr("job_agent.pipeline.evaluate_job", lambda *_: result)
    monkeypatch.setattr(
        "job_agent.pipeline.email_notify",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("email sent")),
    )
    created, alerts = evaluate_for_target(
        session,
        jobs[0],
        {
            "user_id": user.id, "profile": profile,
            "resume_version": "profile-v1", "recipient": user.email,
            "immediate_alerts": True, "daily_digest": True,
        },
        {"immediate_alert_score": 75, "minimum_fit_score": 60,
         "timestamp_policy": {"allow_unverified_current_jobs_in_digest": True}},
        send_notifications=False,
    )
    assert created is True
    assert alerts == 0
    assert session.scalar(select(func.count(Notification.id))) == 0


def test_pending_query_is_postgresql_safe_with_json_job_columns():
    class Results:
        def all(self):
            return []

    class CapturingSession:
        statement = None

        def scalars(self, statement):
            self.statement = statement
            return Results()

    session = CapturingSession()
    request = SimpleNamespace(user_id="user-1", resume_version="profile-v1")
    assert pending_backfill_jobs(session, request, limit=6) == []
    sql = str(session.statement.compile(dialect=postgresql.dialect()))
    assert "SELECT DISTINCT" not in sql.upper()
    assert "user_job_matches" in sql
