from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from job_agent.config import env
from job_agent.models import AuditEvent, AuthToken, User
from job_agent.notify import normalize_email_address


def database_auth_enabled() -> bool:
    return env("AUTH_MODE", "legacy").strip().lower() == "database"


def normalize_login_email(value: str | None) -> str | None:
    normalized = normalize_email_address(value)
    return normalized.lower() if normalized else None


def hash_password(password: str) -> str:
    if len(password) < 12:
        raise ValueError("Password must contain at least 12 characters.")
    salt = os.urandom(16)
    derived = hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=32
    )
    return f"scrypt$16384$8$1${salt.hex()}${derived.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, n, r, p, salt_hex, expected_hex = encoded.split("$", 5)
        if algorithm != "scrypt":
            return False
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=bytes.fromhex(salt_hex),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(bytes.fromhex(expected_hex)),
        )
        return hmac.compare_digest(actual.hex(), expected_hex)
    except (TypeError, ValueError):
        return False


def find_user_by_email(session, email: str | None) -> User | None:
    normalized = normalize_login_email(email)
    if not normalized:
        return None
    return session.scalar(select(User).where(User.email == normalized))


def bootstrap_admin(session) -> User | None:
    existing = session.scalar(select(User).where(User.role == "administrator").limit(1))
    if existing:
        return existing

    email = normalize_login_email(env("ADMIN_EMAIL") or env("ALERT_EMAIL_TO"))
    password = env("ADMIN_PASSWORD", "")
    if not email or len(password) < 12:
        return None

    now = datetime.now(timezone.utc)
    admin = User(
        email=email,
        display_name=env("ADMIN_DISPLAY_NAME", "Administrator"),
        password_hash=hash_password(password),
        role="administrator",
        status="active",
        must_change_password=False,
        created_at=now,
        updated_at=now,
    )
    session.add(admin)
    session.commit()
    return admin


def new_numeric_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def token_digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def utc_aware(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def issue_token(session, user: User, purpose: str, raw_token: str, minutes: int) -> AuthToken:
    now = datetime.now(timezone.utc)
    token = AuthToken(
        user_id=user.id,
        purpose=purpose,
        token_hash=token_digest(raw_token),
        expires_at=now + timedelta(minutes=minutes),
        created_at=now,
    )
    session.add(token)
    session.commit()
    return token


def consume_token(session, user: User, purpose: str, raw_token: str, max_attempts: int = 5) -> bool:
    now = datetime.now(timezone.utc)
    token = session.scalar(
        select(AuthToken)
        .where(
            AuthToken.user_id == user.id,
            AuthToken.purpose == purpose,
            AuthToken.used_at.is_(None),
        )
        .order_by(AuthToken.created_at.desc())
        .limit(1)
    )
    if not token or utc_aware(token.expires_at) < now or token.attempts >= max_attempts:
        return False
    token.attempts += 1
    valid = hmac.compare_digest(token.token_hash, token_digest(raw_token.strip()))
    if valid:
        token.used_at = now
    session.commit()
    return valid


def record_audit(session, event_type: str, actor_user_id=None, target_user_id=None, request=None, detail=None):
    forwarded = request.headers.get("x-forwarded-for", "") if request else ""
    ip_address = forwarded.split(",", 1)[0].strip() or (
        request.client.host if request and request.client else None
    )
    session.add(AuditEvent(
        actor_user_id=actor_user_id,
        target_user_id=target_user_id,
        event_type=event_type,
        detail=detail or {},
        ip_address=ip_address,
        created_at=datetime.now(timezone.utc),
    ))
    session.commit()
