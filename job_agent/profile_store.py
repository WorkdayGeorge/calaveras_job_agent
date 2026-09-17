from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone

from sqlalchemy import select

from .evaluator import load_candidate_profile
from .models import CandidateProfile, User, UserPreference
from .notify import normalize_email_address


PROFILE_LIST_FIELDS = ("career_targets", "experience", "education_training", "truth_constraints")
PROFILE_SKILL_FIELDS = ("accounting_office", "data_technical", "operations", "transferable")


def empty_candidate_profile(user: User) -> dict:
    return {
        "name": user.display_name,
        "location": "",
        "career_targets": [],
        "skills": {key: [] for key in PROFILE_SKILL_FIELDS},
        "experience": [],
        "education_training": [],
        "resume_selection_rules": {
            "focused": ["accounting", "bookkeeping", "administrative", "data entry"],
            "all_work_experience": ["operations", "warehouse", "general labor", "IT support"],
        },
        "truth_constraints": [
            "Use only facts explicitly present in this candidate profile.",
            "Treat coursework and training as training, not employment experience.",
        ],
    }


def validate_candidate_profile(profile: dict) -> list[str]:
    errors = []
    if not isinstance(profile, dict):
        return ["Profile must be a JSON object."]
    for key in ("name", "location"):
        if not isinstance(profile.get(key), str) or not profile[key].strip():
            errors.append(f"{key} must be a non-empty string.")
    for key in PROFILE_LIST_FIELDS:
        if not isinstance(profile.get(key), list):
            errors.append(f"{key} must be a list.")
    skills = profile.get("skills")
    if not isinstance(skills, dict):
        errors.append("skills must be an object.")
    else:
        for key in PROFILE_SKILL_FIELDS:
            if not isinstance(skills.get(key), list):
                errors.append(f"skills.{key} must be a list.")
    rules = profile.get("resume_selection_rules")
    if not isinstance(rules, dict):
        errors.append("resume_selection_rules must be an object.")
    else:
        for key in ("focused", "all_work_experience"):
            if not isinstance(rules.get(key), list):
                errors.append(f"resume_selection_rules.{key} must be a list.")
    return errors


def seed_admin_profile(session, admin: User | None, alert_email: str | None = None) -> None:
    if not admin:
        return
    now = datetime.now(timezone.utc)
    profile = session.get(CandidateProfile, admin.id)
    if not profile:
        profile = CandidateProfile(
            user_id=admin.id,
            profile_data=deepcopy(load_candidate_profile()),
            resume_version="master-profile-v1",
            version=1,
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        session.add(profile)

    preference = session.get(UserPreference, admin.id)
    if not preference:
        recipient = normalize_email_address(alert_email) or admin.email
        preference = UserPreference(
            user_id=admin.id,
            notification_email=recipient,
            immediate_alerts=True,
            daily_digest=True,
            digest_time="17:05",
            created_at=now,
            updated_at=now,
        )
        session.add(preference)
    session.commit()


def ensure_user_profile_records(session, user: User) -> tuple[CandidateProfile, UserPreference]:
    now = datetime.now(timezone.utc)
    profile = session.get(CandidateProfile, user.id)
    if not profile:
        profile = CandidateProfile(
            user_id=user.id,
            profile_data=empty_candidate_profile(user),
            resume_version="profile-v1",
            version=1,
            is_active=False,
            created_at=now,
            updated_at=now,
        )
        session.add(profile)
    preference = session.get(UserPreference, user.id)
    if not preference:
        preference = UserPreference(
            user_id=user.id,
            notification_email=user.email,
            immediate_alerts=True,
            daily_digest=True,
            digest_time="17:05",
            created_at=now,
            updated_at=now,
        )
        session.add(preference)
    session.commit()
    return profile, preference


def active_evaluation_targets(session):
    return session.execute(
        select(User, CandidateProfile, UserPreference)
        .join(CandidateProfile, CandidateProfile.user_id == User.id)
        .join(UserPreference, UserPreference.user_id == User.id)
        .where(
            User.status == "active",
            CandidateProfile.is_active.is_(True),
        )
        .order_by(User.created_at)
    ).all()
