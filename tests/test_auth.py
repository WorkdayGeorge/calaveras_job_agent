from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from job_agent.models import AuthToken, Base, User, UserPreference
from web.auth import (
    bootstrap_admin,
    consume_token,
    hash_password,
    issue_token,
    normalize_login_email,
    set_temporary_password,
    update_user_identity,
    verify_password,
)


def make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def make_user(session):
    now = datetime.now(timezone.utc)
    user = User(
        email="person@example.com",
        display_name="Example Person",
        password_hash=hash_password("temporary-passphrase"),
        role="user",
        status="active",
        must_change_password=True,
        created_at=now,
        updated_at=now,
    )
    session.add(user)
    session.commit()
    return user


def test_password_hash_is_salted_and_verifiable():
    first = hash_password("a-secure-passphrase")
    second = hash_password("a-secure-passphrase")
    assert first != second
    assert verify_password("a-secure-passphrase", first)
    assert not verify_password("wrong-passphrase", first)


def test_password_requires_twelve_characters():
    try:
        hash_password("too-short")
        assert False, "Expected short password to be rejected"
    except ValueError:
        pass


def test_email_normalization_is_case_insensitive():
    assert normalize_login_email(" Person@Example.COM ") == "person@example.com"
    assert normalize_login_email("invalid") is None


def test_one_time_code_can_only_be_consumed_once():
    session = make_session()
    user = make_user(session)
    issue_token(session, user, "login_otp", "123456", minutes=10)
    assert consume_token(session, user, "login_otp", "123456") is True
    assert consume_token(session, user, "login_otp", "123456") is False


def test_wrong_codes_increment_attempts_and_eventually_lock_token():
    session = make_session()
    user = make_user(session)
    token = issue_token(session, user, "login_otp", "654321", minutes=10)
    for _ in range(5):
        assert consume_token(session, user, "login_otp", "000000") is False
    session.refresh(token)
    assert token.attempts == 5
    assert consume_token(session, user, "login_otp", "654321") is False


def test_new_token_invalidates_earlier_unused_token():
    session = make_session()
    user = make_user(session)
    issue_token(session, user, "login_otp", "123456", minutes=10)
    issue_token(session, user, "login_otp", "654321", minutes=10)
    assert consume_token(session, user, "login_otp", "123456") is False
    assert consume_token(session, user, "login_otp", "654321") is True


def test_configured_admin_email_updates_existing_bootstrap_account(monkeypatch):
    session = make_session()
    user = make_user(session)
    user.role = "administrator"
    session.commit()
    monkeypatch.setenv("ADMIN_EMAIL", "MonteGeorgeIII@Gmail.com")
    monkeypatch.setenv("ADMIN_DISPLAY_NAME", "Monte George")

    admin = bootstrap_admin(session)

    assert admin.id == user.id
    assert admin.email == "montegeorgeiii@gmail.com"
    assert admin.display_name == "Monte George"


def test_admin_can_correct_user_email_and_matching_notification_address():
    session = make_session()
    user = make_user(session)
    now = datetime.now(timezone.utc)
    session.add(UserPreference(
        user_id=user.id, notification_email=user.email,
        immediate_alerts=True, daily_digest=True, digest_time="17:05",
        created_at=now, updated_at=now,
    ))
    issue_token(session, user, "password_reset", "old-token", minutes=30)

    update_user_identity(
        session, user, "Corrected@Example.com", "Corrected Name"
    )

    assert user.email == "corrected@example.com"
    assert user.display_name == "Corrected Name"
    assert session.get(UserPreference, user.id).notification_email == user.email
    token = session.query(AuthToken).filter_by(user_id=user.id).one()
    assert token.used_at is not None


def test_email_correction_does_not_overwrite_custom_notification_address():
    session = make_session()
    user = make_user(session)
    now = datetime.now(timezone.utc)
    session.add(UserPreference(
        user_id=user.id, notification_email="alerts@example.net",
        immediate_alerts=True, daily_digest=True, digest_time="17:05",
        created_at=now, updated_at=now,
    ))
    session.commit()
    update_user_identity(session, user, "new@example.com", "New Name")
    assert session.get(UserPreference, user.id).notification_email == "alerts@example.net"


def test_user_email_cannot_collide_with_another_account():
    session = make_session()
    user = make_user(session)
    now = datetime.now(timezone.utc)
    other = User(
        email="other@example.com", display_name="Other User",
        password_hash=hash_password("temporary-passphrase"), role="user",
        status="active", must_change_password=True,
        created_at=now, updated_at=now,
    )
    session.add(other)
    session.commit()
    try:
        update_user_identity(session, user, other.email, "Collision")
        assert False, "Expected duplicate email to be rejected"
    except ValueError as exc:
        assert "another account" in str(exc)


def test_temporary_password_forces_change_and_clears_lockout():
    session = make_session()
    user = make_user(session)
    user.must_change_password = False
    user.failed_login_attempts = 4
    user.locked_until = datetime.now(timezone.utc)
    session.commit()
    set_temporary_password(session, user, "new-temporary-password")
    assert user.must_change_password is True
    assert user.failed_login_attempts == 0
    assert user.locked_until is None
    assert verify_password("new-temporary-password", user.password_hash)
