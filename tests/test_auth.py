from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from job_agent.models import Base, User
from web.auth import (
    consume_token,
    hash_password,
    issue_token,
    normalize_login_email,
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
