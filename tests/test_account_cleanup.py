from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from job_agent.account_cleanup import (
    delete_user_account,
    reset_candidate_data,
)
from job_agent.models import (
    AuditEvent,
    Base,
    CandidateProfile,
    ResumeAsset,
    User,
)


def make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def add_user(session, email="person@example.com", role="user"):
    now = datetime.now(timezone.utc)
    user = User(
        email=email,
        display_name="Same Display Name",
        password_hash="hash",
        role=role,
        status="active",
        must_change_password=False,
        created_at=now,
        updated_at=now,
    )
    session.add(user)
    session.commit()
    return user


def add_candidate_data(session, user):
    now = datetime.now(timezone.utc)
    session.add(CandidateProfile(
        user_id=user.id,
        profile_data={"name": user.display_name},
        resume_version="profile-v1",
        version=1,
        is_active=True,
        created_at=now,
        updated_at=now,
    ))
    session.add(ResumeAsset(
        user_id=user.id,
        resume_type="all-work-experience",
        filename="resume.docx",
        storage_uri="/tmp/resume.docx",
        extracted_text="resume",
        uploaded_at=now,
        is_current=True,
    ))
    session.commit()


def test_candidate_reset_keeps_user_guid_and_clears_candidate_records():
    session = make_session()
    user = add_user(session)
    original_id = user.id
    add_candidate_data(session, user)

    reset_candidate_data(session, user)

    assert session.get(User, original_id) is user
    assert user.status == "onboarding"
    assert session.get(CandidateProfile, original_id) is None
    assert session.query(ResumeAsset).filter_by(user_id=original_id).count() == 0


def test_account_delete_removes_user_and_anonymizes_audit():
    session = make_session()
    user = add_user(session)
    user_id = user.id
    session.add(AuditEvent(
        actor_user_id=user_id,
        target_user_id=user_id,
        event_type="test",
        detail={},
        created_at=datetime.now(timezone.utc),
    ))
    session.commit()

    delete_user_account(session, user)

    assert session.get(User, user_id) is None
    event = session.query(AuditEvent).one()
    assert event.actor_user_id is None
    assert event.target_user_id is None


def test_account_data_page_requires_password_code_and_explicit_confirmation():
    source = open("web/app.py").read()
    template = open("web/templates/account_data.html").read()

    assert 'not verify_password(password, user.password_hash)' in source
    assert 'consume_token(session, user, f"account_{action}", code)' in source
    assert '"administrator"' in source
    assert 'pattern="RESET"' in template
    assert 'pattern="DELETE"' in template
    assert "Account ID" in template
