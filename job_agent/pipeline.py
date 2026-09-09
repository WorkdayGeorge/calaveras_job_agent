\
from __future__ import annotations

from datetime import datetime, timezone, time
from zoneinfo import ZoneInfo

from .config import load_settings, env
from .db import init_db, SessionLocal
from .evaluator import load_candidate_profile, evaluate_job
from .models import Evaluation, Notification, RunLog
from .normalize import normalize_job
from .notify import notification_bucket, console_notify, email_notify
from .providers.demo import DemoProvider
from .providers.adzuna import AdzunaProvider
from .providers.calaveras_county import CalaverasCountyProvider
from .providers.calcareers import CalCareersProvider
from .providers.commonspirit import CommonSpiritProvider
from .providers.bear_valley import BearValleyProvider
from .providers.ccwd import CCWDProvider
from .providers.edjoin_calaveras import EDJoinCalaverasProvider
from .repository import upsert_job, evaluation_exists
from .settings_store import (
    seed_settings, get_bool, get_int, get_setting, enabled_terms
)
from sqlalchemy.exc import IntegrityError

RESUME_VERSION = "master-profile-v1"

def get_providers():
    raw = env("JOB_PROVIDERS") or env("JOB_PROVIDER", "demo") or "demo"
    names = [name.strip().lower() for name in raw.split(",") if name.strip()]

    providers = []

    for name in names:
        if name == "adzuna":
            providers.append(AdzunaProvider())
        elif name == "calaveras_county":
            providers.append(CalaverasCountyProvider())
        elif name == "calcareers":
            providers.append(CalCareersProvider())
        elif name == "commonspirit":
            providers.append(CommonSpiritProvider())
        elif name == "bear_valley":
            providers.append(BearValleyProvider())
        elif name == "ccwd":
            providers.append(CCWDProvider())
        elif name == "edjoin_calaveras":
            providers.append(EDJoinCalaverasProvider())
        elif name == "demo":
            providers.append(DemoProvider())
        else:
            raise ValueError(f"Unknown job provider: {name}")

    return providers

def job_to_dict(job) -> dict:
    return {
        "id": job.id,
        "title": job.title,
        "company": job.company,
        "location": job.location,
        "employment_type": job.employment_type,
        "description": job.description,
        "requirements": job.requirements or [],
        "posted_at": job.posted_at.isoformat() if job.posted_at else None,
        "posted_time_confidence": job.posted_time_confidence,
        "apply_url": job.apply_url,
        "source": job.source,
        "is_local": job.is_local,
        "freshness_status": job.freshness_status,
    }

def _runtime_settings(session, yaml_settings: dict) -> dict:
    settings = dict(yaml_settings)
    settings["fresh_job_window_minutes"] = get_int(
        session, "fresh_job_window_minutes", yaml_settings.get("fresh_job_window_minutes", 60)
    )
    settings["minimum_fit_score"] = get_int(
        session, "minimum_fit_score", yaml_settings.get("minimum_fit_score", 60)
    )
    settings["immediate_alert_score"] = get_int(
        session, "immediate_alert_score", yaml_settings.get("immediate_alert_score", 75)
    )
    settings["timestamp_policy"] = dict(yaml_settings.get("timestamp_policy", {}))
    settings["timestamp_policy"]["allow_unverified_current_jobs_in_digest"] = get_bool(
        session, "allow_unverified_current_jobs_in_digest", True
    )
    return settings

PACIFIC_TZ = ZoneInfo("America/Los_Angeles")


def scheduled_run_allowed(session) -> tuple[bool, str]:
    """Return whether a scheduled search should run right now."""
    now = datetime.now(PACIFIC_TZ)

    days_raw = get_setting(session, "schedule_days", "0,1,2,3,4") or ""
    try:
        active_days = {
            int(value)
            for value in days_raw.split(",")
            if value.strip()
        }
    except ValueError:
        active_days = {0, 1, 2, 3, 4}

    if now.weekday() not in active_days:
        return False, "inactive day"

    start_raw = get_setting(session, "schedule_start_time", "09:00") or "09:00"
    stop_raw = get_setting(session, "schedule_stop_time", "17:00") or "17:00"

    try:
        start_time = time.fromisoformat(start_raw)
        stop_time = time.fromisoformat(stop_raw)
    except ValueError:
        start_time = time(9, 0)
        stop_time = time(17, 0)

    current_time = now.time().replace(second=0, microsecond=0)

    if current_time < start_time or current_time > stop_time:
        return False, "outside active hours"

    interval = get_int(session, "schedule_interval_minutes", 15)
    if interval not in {5, 10, 15, 30, 60}:
        interval = 15

    start_minutes = start_time.hour * 60 + start_time.minute
    current_minutes = now.hour * 60 + now.minute
    minutes_since_start = current_minutes - start_minutes

    if minutes_since_start % interval != 0:
        return False, "not an interval boundary"

    return True, "scheduled run allowed"

def run_once(force: bool = False) -> dict:
    yaml_settings = load_settings()
    profile = load_candidate_profile()
    init_db()

    with SessionLocal() as session:
        seed_settings(session, yaml_settings)

        if not force and not get_bool(session, "agent_enabled", True):
            summary = {"status": "paused", "found": 0, "new_local_jobs": 0, "evaluated": 0, "alerts": 0}
            print("Run skipped: agent is paused.")
            return summary

        if not force:
            allowed, reason = scheduled_run_allowed(session)
            if not allowed:
                summary = {
                    "status": "schedule_skipped",
                    "reason": reason,
                    "found": 0,
                    "new_local_jobs": 0,
                    "evaluated": 0,
                    "alerts": 0,
                }
                print(f"Run skipped: {reason}.")
                return summary

        settings = _runtime_settings(session, yaml_settings)
        terms = enabled_terms(session)
        providers = get_providers()
        provider_names = ",".join(type(p).__name__.replace("Provider", "").lower() for p in providers)

        run = RunLog(
            started_at=datetime.now(timezone.utc),
            status="running",
            provider=provider_names,
        )
        session.add(run)
        session.commit()
        session.refresh(run)

        found = inserted = evaluated = alerts = 0
        now = datetime.now(timezone.utc)
        processed_job_ids = set()
        try:
            for provider in providers:
                for role in terms:
                    raw_jobs = provider.search(
                        role=role,
                        location=settings["location"]["primary"],
                        results_per_page=25,
                    )
                    found += len(raw_jobs)

                    for raw in raw_jobs:
                        normalized = normalize_job(raw, settings, now=now)
                        if not normalized.is_local:
                            continue
    
                        job, is_new = upsert_job(session, normalized)
                        if is_new:
                            inserted += 1
    
                        if job.id in processed_job_ids:
                            continue

                        if evaluation_exists(session, job.id, RESUME_VERSION):
                            processed_job_ids.add(job.id)
                            continue

                        processed_job_ids.add(job.id)
    
                        job_dict = job_to_dict(job)
                        result = evaluate_job(job_dict, profile)
                        evaluation = Evaluation(
                            job_id=job.id,
                            resume_version=RESUME_VERSION,
                            fit_score=int(result["fit_score"]),
                            classification=result["classification"],
                            recommendation=result["recommendation"],
                            selected_resume=result["selected_resume"],
                            matching_skills=result.get("matching_skills", []),
                            transferable_skills=result.get("transferable_skills", []),
                            missing_requirements=result.get("missing_requirements", []),
                            uncertain_requirements=result.get("uncertain_requirements", []),
                            reasoning=result["reasoning"],
                            score_breakdown=result.get("score_breakdown", {}),
                            evaluated_at=datetime.now(timezone.utc),
                        )
                        session.add(evaluation)

                        try:
                            session.commit()
                            session.refresh(evaluation)
                        except IntegrityError:
                            session.rollback()
                            continue

                        evaluated += 1
    
                        bucket = notification_bucket(job_dict, result, settings)
                        if bucket != "silent":
                            alerts += 1
                            console_notify(job_dict, result, bucket)
                            sent, detail = email_notify(job_dict, result, bucket)
                            session.add(Notification(
                                job_id=job.id,
                                evaluation_id=evaluation.id,
                                channel="email" if sent else "console",
                                sent_at=datetime.now(timezone.utc),
                                status="sent" if sent else "not_sent",
                                detail=detail,
                            ))
                            session.commit()

            run.finished_at = datetime.now(timezone.utc)
            run.status = "success"
            run.found = found
            run.new_local_jobs = inserted
            run.evaluated = evaluated
            run.alerts = alerts
            session.commit()

            summary = {
                "status": "success",
                "provider": provider_names,
                "found": found,
                "new_local_jobs": inserted,
                "evaluated": evaluated,
                "alerts": alerts,
            }
            print("\nRun summary:", summary)
            return summary

        except Exception as exc:
            session.rollback()
            run.finished_at = datetime.now(timezone.utc)
            run.status = "error"
            run.found = found
            run.new_local_jobs = inserted
            run.evaluated = evaluated
            run.alerts = alerts
            run.error = str(exc)
            session.commit()
            raise

if __name__ == "__main__":
    run_once()
