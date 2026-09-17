\
from __future__ import annotations

from datetime import datetime, timezone, time, timedelta
from zoneinfo import ZoneInfo

from .config import load_settings, env
from .db import init_db, SessionLocal
from .evaluator import load_candidate_profile, evaluate_job
from .models import Job, Evaluation, Notification, RunLog, User
from .normalize import normalize_job
from .notify import notification_bucket, console_notify, email_notify, email_high_priority_digest
from .providers.demo import DemoProvider
from .providers.adzuna import AdzunaProvider
from .providers.calaveras_county import CalaverasCountyProvider
from .providers.calcareers import CalCareersProvider
from .providers.commonspirit import CommonSpiritProvider
from .providers.bear_valley import BearValleyProvider
from .providers.ccwd import CCWDProvider
from .providers.amador_water import AmadorWaterAgencyProvider
from .providers.tuolumne_utilities import TuolumneUtilitiesProvider
from .providers.edjoin_calaveras import EDJoinCalaverasProvider
from .providers.edjoin_amador import EDJoinAmadorProvider
from .providers.edjoin_tuolumne import EDJoinTuolumneProvider
from .providers.adventist_health import AdventistHealthProvider
from .providers.pge import PGEProvider
from .providers.usajobs import USAJobsProvider
from .providers.amador_county import AmadorCountyProvider
from .providers.tuolumne_county import TuolumneCountyProvider
from .providers.worldmark_angels_camp import WorldMarkAngelsCampProvider
from .repository import upsert_job, evaluation_exists
from .profile_store import active_evaluation_targets
from .settings_store import (
    seed_settings, get_bool, get_int, get_setting, set_setting, enabled_terms
)
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

RESUME_VERSION = "master-profile-v1"


def evaluation_targets(session) -> list[dict]:
    targets = []
    for user, profile, preference in active_evaluation_targets(session):
        targets.append({
            "user_id": user.id,
            "profile": profile.profile_data,
            "resume_version": profile.resume_version,
            "recipient": preference.notification_email,
            "immediate_alerts": preference.immediate_alerts,
            "daily_digest": preference.daily_digest,
            "digest_time": preference.digest_time,
            "preference": preference,
        })
    if targets:
        return targets
    return [{
        "user_id": None,
        "profile": load_candidate_profile(),
        "resume_version": RESUME_VERSION,
        "recipient": (
            get_setting(session, "alert_email_to", env("ALERT_EMAIL_TO", ""))
            or env("ALERT_EMAIL_TO", "")
        ),
        "immediate_alerts": True,
        "daily_digest": True,
        "digest_time": get_setting(session, "high_priority_digest_time", "17:05") or "17:05",
        "preference": None,
    }]

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
        elif name == "amador_water":
            providers.append(AmadorWaterAgencyProvider())
        elif name == "tuolumne_utilities":
            providers.append(TuolumneUtilitiesProvider())
        elif name == "edjoin_calaveras":
            providers.append(EDJoinCalaverasProvider())
        elif name == "edjoin_amador":
            providers.append(EDJoinAmadorProvider())
        elif name == "edjoin_tuolumne":
            providers.append(EDJoinTuolumneProvider())
        elif name == "adventist_health":
            providers.append(AdventistHealthProvider())
        elif name == "pge":
            providers.append(PGEProvider())
        elif name == "usajobs":
            providers.append(USAJobsProvider())
        elif name == "amador_county":
            providers.append(AmadorCountyProvider())
        elif name == "tuolumne_county":
            providers.append(TuolumneCountyProvider())
        elif name == "worldmark_angels_camp":
            providers.append(WorldMarkAngelsCampProvider())
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
    settings["alert_email_to"] = (
        get_setting(session, "alert_email_to", env("ALERT_EMAIL_TO", ""))
        or env("ALERT_EMAIL_TO", "")
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

def process_high_priority_digest(session) -> dict:
    """Send an isolated daily digest to each active profile."""
    now_pt = datetime.now(PACIFIC_TZ)
    today = now_pt.date().isoformat()
    results = []
    immediate_alert_score = get_int(session, "immediate_alert_score", 75)
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)

    for target in evaluation_targets(session):
        if not target["daily_digest"]:
            continue
        try:
            digest_time = time.fromisoformat(target["digest_time"])
        except ValueError:
            digest_time = time(17, 5)
        if now_pt.time().replace(second=0, microsecond=0) < digest_time:
            continue
        preference = target["preference"]
        last_date = (
            preference.last_digest_date
            if preference
            else (get_setting(session, "high_priority_digest_last_date", "") or "")
        )
        if last_date == today:
            continue

        owner_id = target["user_id"]
        rows = session.execute(
            select(Notification, Job, Evaluation)
            .join(Job, Notification.job_id == Job.id)
            .join(Evaluation, Notification.evaluation_id == Evaluation.id)
            .where(
                Notification.status == "pending_digest",
                Notification.user_id == owner_id,
            )
            .order_by(Evaluation.fit_score.desc(), Job.first_seen_at.desc())
        ).all()
        recent_rows = session.execute(
            select(Job, Evaluation)
            .join(Evaluation, Evaluation.job_id == Job.id)
            .where(
                Evaluation.user_id == owner_id,
                Evaluation.evaluated_at >= cutoff,
                Evaluation.fit_score >= immediate_alert_score,
            )
            .order_by(Evaluation.fit_score.desc(), Evaluation.evaluated_at.desc())
        ).all()

        if not rows and not recent_rows:
            if preference:
                preference.last_digest_date = today
            else:
                set_setting(session, "high_priority_digest_last_date", today)
            session.commit()
            results.append({"user_id": owner_id, "status": "no items"})
            continue

        items = [(job_to_dict(job), {
            "fit_score": evaluation.fit_score,
            "classification": evaluation.classification,
            "recommendation": evaluation.recommendation,
        }) for _, job, evaluation in rows]
        recent_items = [(job_to_dict(job), {
            "fit_score": evaluation.fit_score,
            "classification": evaluation.classification,
            "recommendation": evaluation.recommendation,
            "evaluated_at": evaluation.evaluated_at.isoformat(),
        }) for job, evaluation in recent_rows]
        sent, detail = email_high_priority_digest(
            items,
            recipient=target["recipient"],
            recent_immediate_items=recent_items,
            immediate_alert_score=immediate_alert_score,
        )
        if not sent:
            results.append({"user_id": owner_id, "status": "failed", "detail": detail})
            continue

        sent_at = datetime.now(timezone.utc)
        for notification, _, _ in rows:
            notification.status = "sent"
            notification.channel = "digest"
            notification.sent_at = sent_at
            notification.detail = "Sent in daily high-priority digest"
        if preference:
            preference.last_digest_date = today
        else:
            set_setting(session, "high_priority_digest_last_date", today)
        session.commit()
        results.append({"user_id": owner_id, "status": "sent", "count": len(rows)})

    return {"status": "processed", "results": results}

def run_once(force: bool = False) -> dict:
    yaml_settings = load_settings()
    init_db()

    with SessionLocal() as session:
        seed_settings(session, yaml_settings)
        targets = evaluation_targets(session)

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
                digest_result = process_high_priority_digest(session)
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
        provider_errors = []
        try:
            for provider in providers:
                provider_name = type(provider).__name__.replace("Provider", "")
                for role in terms:
                    if isinstance(provider, AdzunaProvider):
                        search_locations = (
                            settings["location"].get("search_locations")
                            or [settings["location"]["primary"]]
                        )
                    else:
                        search_locations = [
                            settings["location"]["primary"]
                        ]
                    raw_jobs = []
                    for search_location in search_locations:
                        try:
                            raw_jobs.extend(
                                provider.search(
                                    role=role,
                                    location=search_location,
                                    results_per_page=25,
                                )
                            )
                        except Exception as exc:
                            message = (
                                f"{provider_name} search failed for {role!r} "
                                f"in {search_location!r}: {exc}"
                            )
                            provider_errors.append(message)
                            print(message)

                    found += len(raw_jobs)

                    for raw in raw_jobs:
                        normalized = normalize_job(raw, settings, now=now)
                        if not normalized.is_local:
                            continue
    
                        job, is_new = upsert_job(session, normalized)
                        if is_new:
                            inserted += 1
    
                        job_dict = job_to_dict(job)
                        for target in targets:
                            owner_id = target["user_id"]
                            resume_version = target["resume_version"]
                            process_key = (job.id, owner_id, resume_version)
                            if process_key in processed_job_ids:
                                continue
                            processed_job_ids.add(process_key)
                            if evaluation_exists(
                                session, job.id, resume_version, owner_id
                            ):
                                continue

                            try:
                                result = evaluate_job(job_dict, target["profile"])
                            except Exception as exc:
                                message = (
                                    "Evaluation failed for job "
                                    f"{job.id} and user {owner_id or 'legacy'}: {exc}"
                                )
                                provider_errors.append(message)
                                print(message)
                                continue
                            evaluation = Evaluation(
                                user_id=owner_id,
                                job_id=job.id,
                                resume_version=resume_version,
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
                            target_settings = dict(settings)
                            target_settings["alert_email_to"] = target["recipient"]
                            bucket = notification_bucket(job_dict, result, target_settings)
                            if (
                                bucket == "high_priority_digest"
                                and target["daily_digest"]
                            ):
                                session.add(Notification(
                                    user_id=owner_id,
                                    job_id=job.id,
                                    evaluation_id=evaluation.id,
                                    channel="digest",
                                    sent_at=datetime.now(timezone.utc),
                                    status="pending_digest",
                                    detail="Queued for daily high-priority digest",
                                ))
                                session.commit()
                            elif bucket != "silent":
                                if target["immediate_alerts"]:
                                    alerts += 1
                                    console_notify(job_dict, result, bucket)
                                    sent, detail = email_notify(
                                        job_dict,
                                        result,
                                        bucket,
                                        recipient=target["recipient"],
                                    )
                                    session.add(Notification(
                                        user_id=owner_id,
                                        job_id=job.id,
                                        evaluation_id=evaluation.id,
                                        channel="email" if sent else "console",
                                        sent_at=datetime.now(timezone.utc),
                                        status="sent" if sent else "not_sent",
                                        detail=detail,
                                    ))
                                    session.commit()
                                elif target["daily_digest"]:
                                    session.add(Notification(
                                        user_id=owner_id,
                                        job_id=job.id,
                                        evaluation_id=evaluation.id,
                                        channel="digest",
                                        sent_at=datetime.now(timezone.utc),
                                        status="pending_digest",
                                        detail="Queued because immediate alerts are disabled",
                                    ))
                                    session.commit()

            run.finished_at = datetime.now(timezone.utc)
            run.status = "partial" if provider_errors else "success"
            run.found = found
            run.new_local_jobs = inserted
            run.evaluated = evaluated
            run.alerts = alerts
            run.error = "\n".join(provider_errors) if provider_errors else None
            session.commit()

            digest_result = process_high_priority_digest(session)

            summary = {
                "status": run.status,
                "provider": provider_names,
                "found": found,
                "new_local_jobs": inserted,
                "evaluated": evaluated,
                "alerts": alerts,
                "provider_errors": provider_errors,
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
