\
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone

from .config import load_settings, env
from .db import init_db, SessionLocal
from .evaluator import load_candidate_profile, evaluate_job
from .models import Evaluation
from .normalize import normalize_job
from .notify import notification_bucket, console_notify
from .providers.demo import DemoProvider
from .providers.adzuna import AdzunaProvider
from .repository import upsert_job, evaluation_exists

RESUME_VERSION = "master-profile-v1"

def get_provider():
    name = (env("JOB_PROVIDER", "demo") or "demo").lower()
    if name == "adzuna":
        return AdzunaProvider()
    if name == "demo":
        return DemoProvider()
    raise ValueError(f"Unknown JOB_PROVIDER={name}")

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

def run_once() -> dict:
    settings = load_settings()
    profile = load_candidate_profile()
    provider = get_provider()
    init_db()

    found = inserted = evaluated = alerts = 0
    now = datetime.now(timezone.utc)

    with SessionLocal() as session:
        for role in settings["categories"]:
            raw_jobs = provider.search(
                role=role,
                location=settings["location"]["primary"],
                results_per_page=25,
            )
            found += len(raw_jobs)

            for raw in raw_jobs:
                normalized = normalize_job(raw, settings, now=now)

                # Strict county/locality filter.
                if not normalized.is_local:
                    continue

                job, is_new = upsert_job(session, normalized)
                if is_new:
                    inserted += 1

                # Evaluate once per master-profile version.
                if evaluation_exists(session, job.id, RESUME_VERSION):
                    continue

                job_dict = job_to_dict(job)
                result = evaluate_job(job_dict, profile)
                evaluated += 1

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
                session.commit()

                bucket = notification_bucket(job_dict, result, settings)
                if bucket != "silent":
                    alerts += 1
                    console_notify(job_dict, result, bucket)

    summary = {
        "provider": env("JOB_PROVIDER", "demo"),
        "found": found,
        "new_local_jobs": inserted,
        "evaluated": evaluated,
        "alerts": alerts,
    }
    print("\nRun summary:", summary)
    return summary

if __name__ == "__main__":
    run_once()
