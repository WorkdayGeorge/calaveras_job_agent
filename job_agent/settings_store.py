\
from __future__ import annotations

from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.orm import Session
from .models import AppSetting, SearchTerm

DEFAULTS = {
    "agent_enabled": "true",
    "fresh_job_window_minutes": "60",
    "minimum_fit_score": "60",
    "immediate_alert_score": "75",
    "allow_unverified_current_jobs_in_digest": "true",
    "schedule_interval_minutes": "15",
    "schedule_start_time": "09:00",
    "schedule_stop_time": "17:00",
    "schedule_days": "0,1,2,3,4",



}

def seed_settings(session: Session, yaml_settings: dict) -> None:
    now = datetime.now(timezone.utc)
    defaults = dict(DEFAULTS)
    defaults["fresh_job_window_minutes"] = str(yaml_settings.get("fresh_job_window_minutes", 60))
    defaults["minimum_fit_score"] = str(yaml_settings.get("minimum_fit_score", 60))
    defaults["immediate_alert_score"] = str(yaml_settings.get("immediate_alert_score", 75))
    defaults["allow_unverified_current_jobs_in_digest"] = str(
        yaml_settings.get("timestamp_policy", {}).get("allow_unverified_current_jobs_in_digest", True)
    ).lower()

    for key, value in defaults.items():
        if session.get(AppSetting, key) is None:
            session.add(AppSetting(key=key, value=value, updated_at=now))

    existing_terms = {r[0] for r in session.execute(select(SearchTerm.term)).all()}
    for term in yaml_settings.get("categories", []):
        if term not in existing_terms:
            session.add(SearchTerm(term=term, enabled=True, created_at=now))
    session.commit()

def get_setting(session: Session, key: str, default: str | None = None) -> str | None:
    obj = session.get(AppSetting, key)
    return obj.value if obj else default

def get_bool(session: Session, key: str, default: bool = False) -> bool:
    raw = get_setting(session, key, str(default).lower())
    return str(raw).lower() in {"1", "true", "yes", "on"}

def get_int(session: Session, key: str, default: int) -> int:
    raw = get_setting(session, key, str(default))
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default

def set_setting(session: Session, key: str, value: str) -> None:
    now = datetime.now(timezone.utc)
    obj = session.get(AppSetting, key)
    if obj:
        obj.value = value
        obj.updated_at = now
    else:
        session.add(AppSetting(key=key, value=value, updated_at=now))
    session.commit()

def enabled_terms(session: Session) -> list[str]:
    rows = session.scalars(
        select(SearchTerm).where(SearchTerm.enabled.is_(True)).order_by(SearchTerm.term)
    ).all()
    return [x.term for x in rows]
