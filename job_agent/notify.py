\
from __future__ import annotations

def notification_bucket(job: dict, evaluation: dict, settings: dict) -> str:
    score = int(evaluation["fit_score"])
    fresh = job.get("freshness_status") == "verified_fresh"

    if fresh and score >= settings["immediate_alert_score"]:
        return "immediate"
    if fresh and score >= settings["minimum_fit_score"]:
        return "immediate_possible_fit"
    if (not fresh) and score >= settings["immediate_alert_score"] and settings["timestamp_policy"]["allow_unverified_current_jobs_in_digest"]:
        return "high_priority_digest"
    return "silent"

def console_notify(job: dict, evaluation: dict, bucket: str) -> None:
    if bucket == "silent":
        return
    print("\n" + "=" * 72)
    print(f"{bucket.upper()}: {job['title']} — {job['company']}")
    print(f"Location: {job.get('location')}")
    print(f"Freshness: {job.get('freshness_status')}")
    print(f"Fit: {evaluation['fit_score']}/100 — {evaluation['classification']}")
    print(f"Recommendation: {evaluation['recommendation']}")
    print(f"Resume: {evaluation['selected_resume']}")
    print(f"Apply: {job['apply_url']}")
    print(f"Why: {evaluation['reasoning']}")
    print("=" * 72)
