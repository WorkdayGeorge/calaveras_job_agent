from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from job_agent.models import Base, SearchTerm, User, UserOnboarding
from job_agent.user_search import ensure_user_search_terms
from web.app import (
    default_signed_in_destination,
    require_admin_or_self,
    user_onboarding_complete,
)
from web.auth import consume_token, find_valid_token, hash_password, issue_token


def make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def add_user(session, email="invited@example.com", status="invited"):
    now = datetime.now(timezone.utc)
    user = User(
        email=email,
        display_name="Invited User",
        password_hash=hash_password("unusable-temporary-password"),
        role="user",
        status=status,
        must_change_password=True,
        created_at=now,
        updated_at=now,
    )
    session.add(user)
    session.commit()
    return user


def request_for(user_id, role="user"):
    return SimpleNamespace(
        session={"user_id": user_id, "role": role},
        url=SimpleNamespace(path="/profile"),
    )


def test_invitation_token_is_single_use_and_time_limited():
    session = make_session()
    user = add_user(session)
    issue_token(session, user, "onboarding_invite", "private-link", minutes=60)

    token = find_valid_token(session, "onboarding_invite", "private-link")
    assert token.user_id == user.id
    assert find_valid_token(session, "onboarding_invite", "wrong") is None

    assert consume_token(session, user, "onboarding_invite", "private-link") is True
    assert find_valid_token(session, "onboarding_invite", "private-link") is None


def test_invited_users_choose_search_terms_instead_of_inheriting_defaults():
    session = make_session()
    user = add_user(session)
    now = datetime.now(timezone.utc)
    session.add(SearchTerm(term="Legacy Default", enabled=True, created_at=now))
    session.add(UserOnboarding(
        user_id=user.id,
        invited_at=now,
        invitation_expires_at=now + timedelta(hours=48),
        updated_at=now,
    ))
    session.commit()

    assert ensure_user_search_terms(session, user) == []


def test_existing_users_keep_legacy_search_term_initialization():
    session = make_session()
    user = add_user(session, "existing@example.com", status="active")
    session.add(SearchTerm(
        term="Accounting Clerk",
        enabled=True,
        created_at=datetime.now(timezone.utc),
    ))
    session.commit()

    terms = ensure_user_search_terms(session, user)

    assert [term.term for term in terms] == ["Accounting Clerk"]
    assert session.get(UserOnboarding, user.id) is None
    assert user_onboarding_complete(session, user) is True
    assert default_signed_in_destination(session, user) == "/jobs"


def test_incomplete_onboarding_users_are_sent_to_setup_then_jobs():
    session = make_session()
    user = add_user(session, status="onboarding")
    now = datetime.now(timezone.utc)
    onboarding = UserOnboarding(
        user_id=user.id,
        invited_at=now,
        invitation_expires_at=now + timedelta(hours=48),
        updated_at=now,
    )
    session.add(onboarding)
    session.commit()

    assert user_onboarding_complete(session, user) is False
    assert default_signed_in_destination(session, user) == "/onboarding"

    onboarding.completed_at = now
    session.commit()
    assert default_signed_in_destination(session, user) == "/jobs"


def test_administrator_keeps_dashboard_destination():
    session = make_session()
    user = add_user(session, status="active")
    user.role = "administrator"
    session.commit()

    assert default_signed_in_destination(session, user) == "/"


def test_users_can_manage_only_their_own_profile():
    assert require_admin_or_self(request_for("user-1"), "user-1") is None
    assert require_admin_or_self(request_for("user-1"), "user-2").status_code == 403
    assert require_admin_or_self(
        request_for("admin-1", role="administrator"), "user-2"
    ) is None


def test_admin_user_form_is_invitation_only():
    from pathlib import Path

    template = (
        Path(__file__).resolve().parents[1]
        / "web"
        / "templates"
        / "users.html"
    ).read_text()
    assert "Send invitation" in template
    assert 'name="temporary_password"' not in template
