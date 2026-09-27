from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from job_agent.application_assistant import (
    ensure_assistant_profile,
    normalize_assistant_data,
    save_assistant_profile,
    user_for_extension_token,
)
from job_agent.models import Base, User
from web.auth import hash_password, issue_token


def make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def add_user(session, email="assistant@example.com"):
    now = datetime.now(timezone.utc)
    user = User(
        email=email,
        display_name="Application User",
        password_hash=hash_password("temporary-password"),
        role="user",
        status="active",
        must_change_password=False,
        created_at=now,
        updated_at=now,
    )
    session.add(user)
    session.commit()
    return user


def test_new_assistant_profile_uses_review_safe_defaults():
    session = make_session()
    user = add_user(session)

    profile = ensure_assistant_profile(session, user)

    assert profile.contact_data["country"] == "United States"
    assert profile.standard_answers["authorized_to_work"] == "review"
    assert profile.standard_answers["requires_sponsorship"] == "review"
    assert profile.standard_answers["willing_to_relocate"] == "review"


def test_assistant_profile_saves_only_known_fields():
    session = make_session()
    user = add_user(session)

    profile = save_assistant_profile(
        session,
        user,
        {"phone": " 555-0100 ", "unknown": "discard"},
        {"authorized_to_work": "YES", "unknown": "discard"},
    )

    assert profile.contact_data["phone"] == "555-0100"
    assert "unknown" not in profile.contact_data
    assert profile.standard_answers["authorized_to_work"] == "yes"
    assert "unknown" not in profile.standard_answers


def test_invalid_standard_choice_is_rejected():
    try:
        normalize_assistant_data({}, {"requires_sponsorship": "sometimes"})
        assert False, "Expected an invalid choice to be rejected"
    except ValueError as exc:
        assert "requires_sponsorship" in str(exc)


def test_extension_token_resolves_only_an_active_ready_user():
    session = make_session()
    user = add_user(session)
    issue_token(
        session,
        user,
        "application_assistant",
        "secret-extension-token",
        minutes=60,
    )

    assert user_for_extension_token(session, "secret-extension-token").id == user.id
    assert user_for_extension_token(session, "wrong-token") is None

    user.status = "suspended"
    session.commit()
    assert user_for_extension_token(session, "secret-extension-token") is None
