from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from job_agent.models import (
    Base, CandidateProfile, Evaluation, Job, Notification, User, UserPreference,
)
from job_agent.pipeline import process_high_priority_digest
from job_agent.profile_store import (
    active_evaluation_targets,
    ensure_user_profile_records,
    seed_admin_profile,
    validate_candidate_profile,
)
from web.auth import hash_password


def make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def add_user(session, email="person@example.com", role="user"):
    now = datetime.now(timezone.utc)
    user = User(
        email=email,
        display_name="Example Person",
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


def valid_profile(name="Example Person"):
    return {
        "name": name,
        "location": "Avery, CA",
        "career_targets": ["accounting assistant"],
        "skills": {
            "accounting_office": ["Excel"],
            "data_technical": [],
            "operations": [],
            "transferable": ["Customer service"],
        },
        "experience": [],
        "education_training": [],
        "resume_selection_rules": {
            "focused": ["accounting"],
            "all_work_experience": ["operations"],
        },
        "truth_constraints": ["Do not invent qualifications."],
    }


def test_new_user_profile_is_inactive_until_admin_approval():
    session = make_session()
    user = add_user(session)
    profile, preference = ensure_user_profile_records(session, user)
    assert profile.is_active is False
    assert profile.profile_data["name"] == "Example Person"
    assert preference.notification_email == user.email
    assert active_evaluation_targets(session) == []


def test_active_profiles_become_independent_evaluation_targets():
    session = make_session()
    first = add_user(session, "first@example.com")
    second = add_user(session, "second@example.com")
    first_profile, first_preference = ensure_user_profile_records(session, first)
    second_profile, second_preference = ensure_user_profile_records(session, second)
    first_profile.profile_data = valid_profile("First")
    second_profile.profile_data = valid_profile("Second")
    first_profile.is_active = True
    second_profile.is_active = True
    first_preference.notification_email = "first-alerts@example.com"
    second_preference.notification_email = "second-alerts@example.com"
    session.commit()

    targets = active_evaluation_targets(session)
    assert [row[0].id for row in targets] == [first.id, second.id]
    assert targets[0][1].profile_data["name"] == "First"
    assert targets[1][2].notification_email == "second-alerts@example.com"


def test_admin_seed_preserves_master_profile_identity(monkeypatch):
    session = make_session()
    admin = add_user(session, "admin@example.com", role="administrator")
    monkeypatch.setattr(
        "job_agent.profile_store.load_candidate_profile",
        lambda: valid_profile("Joshua George"),
    )
    seed_admin_profile(session, admin, "jobs@example.com")
    seed_admin_profile(session, admin, "different@example.com")

    profile = session.get(CandidateProfile, admin.id)
    preference = session.get(UserPreference, admin.id)
    assert profile.resume_version == "master-profile-v1"
    assert profile.is_active is True
    assert preference.notification_email == "jobs@example.com"


def test_profile_validation_rejects_missing_truth_structure():
    profile = valid_profile()
    profile["skills"].pop("accounting_office")
    errors = validate_candidate_profile(profile)
    assert "skills.accounting_office must be a list." in errors


def test_daily_digests_are_separated_by_user(monkeypatch):
    session = make_session()
    sent = []
    now = datetime.now(timezone.utc)
    for index in (1, 2):
        user = add_user(session, f"user{index}@example.com")
        profile, preference = ensure_user_profile_records(session, user)
        profile.profile_data = valid_profile(f"User {index}")
        profile.is_active = True
        preference.digest_time = "00:00"
        job = Job(
            title=f"Private Job {index}",
            company="Example",
            apply_url=f"https://example.com/{index}",
            first_seen_at=now,
            last_seen_at=now,
            job_fingerprint=str(index) * 64,
            is_local=True,
            freshness_status="unverified",
        )
        session.add(job)
        session.flush()
        evaluation = Evaluation(
            user_id=user.id,
            job_id=job.id,
            resume_version="profile-v1",
            fit_score=80,
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
            channel="digest",
            sent_at=now,
            status="pending_digest",
        ))
    session.commit()

    def fake_digest(items, recipient=None, **kwargs):
        sent.append((recipient, [job["title"] for job, _ in items]))
        return True, "sent"

    monkeypatch.setattr("job_agent.pipeline.email_high_priority_digest", fake_digest)
    process_high_priority_digest(session)
    assert sent == [
        ("user1@example.com", ["Private Job 1"]),
        ("user2@example.com", ["Private Job 2"]),
    ]
