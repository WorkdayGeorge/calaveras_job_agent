from __future__ import annotations

from datetime import datetime, timezone
import hashlib

from sqlalchemy import select

from .models import ApplicationAssistantProfile, AuthToken, User


CONTACT_FIELDS = (
    "phone",
    "address_line_1",
    "address_line_2",
    "city",
    "state",
    "postal_code",
    "country",
    "linkedin_url",
)

ANSWER_FIELDS = (
    "authorized_to_work",
    "requires_sponsorship",
    "willing_to_relocate",
    "available_start_date",
    "desired_salary",
    "remote_preference",
)

CHOICE_FIELDS = {
    "authorized_to_work",
    "requires_sponsorship",
    "willing_to_relocate",
}

ALLOWED_CHOICES = {"", "yes", "no", "review"}


def ensure_assistant_profile(session, user: User) -> ApplicationAssistantProfile:
    profile = session.get(ApplicationAssistantProfile, user.id)
    if profile:
        return profile
    now = datetime.now(timezone.utc)
    profile = ApplicationAssistantProfile(
        user_id=user.id,
        contact_data={
            **{key: "" for key in CONTACT_FIELDS},
            "country": "United States",
        },
        standard_answers={
            **{key: "" for key in ANSWER_FIELDS},
            "authorized_to_work": "review",
            "requires_sponsorship": "review",
            "willing_to_relocate": "review",
        },
        created_at=now,
        updated_at=now,
    )
    session.add(profile)
    session.commit()
    return profile


def normalize_assistant_data(contact_data: dict, standard_answers: dict) -> tuple[dict, dict]:
    contact = {
        key: str(contact_data.get(key) or "").strip()
        for key in CONTACT_FIELDS
    }
    answers = {
        key: str(standard_answers.get(key) or "").strip()
        for key in ANSWER_FIELDS
    }
    for key in CHOICE_FIELDS:
        value = answers[key].casefold()
        if value not in ALLOWED_CHOICES:
            raise ValueError(f"Invalid selection for {key}.")
        answers[key] = value
    return contact, answers


def save_assistant_profile(
    session,
    user: User,
    contact_data: dict,
    standard_answers: dict,
) -> ApplicationAssistantProfile:
    contact, answers = normalize_assistant_data(contact_data, standard_answers)
    profile = ensure_assistant_profile(session, user)
    profile.contact_data = contact
    profile.standard_answers = answers
    profile.updated_at = datetime.now(timezone.utc)
    session.commit()
    return profile


def user_for_extension_token(session, raw_token: str | None) -> User | None:
    if not raw_token:
        return None
    now = datetime.now(timezone.utc)
    digest = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    token = session.scalar(
        select(AuthToken)
        .where(
            AuthToken.purpose == "application_assistant",
            AuthToken.token_hash == digest,
            AuthToken.used_at.is_(None),
        )
        .order_by(AuthToken.created_at.desc())
        .limit(1)
    )
    expires_at = token.expires_at if token else None
    if expires_at is not None and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if not token or expires_at < now:
        return None
    user = session.get(User, token.user_id)
    if (
        not user
        or user.status not in {"active", "onboarding"}
        or user.must_change_password
    ):
        return None
    return user
