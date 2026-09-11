\
from __future__ import annotations

import smtplib
from email.message import EmailMessage
from datetime import datetime, timezone

from .config import env

def notification_bucket(job: dict, evaluation: dict, settings: dict) -> str:
    score = int(evaluation["fit_score"])
    fresh = job.get("freshness_status") == "verified_fresh"

    if fresh and score >= settings["immediate_alert_score"]:
        return "immediate"
    if fresh and score >= settings["minimum_fit_score"]:
        return "immediate_possible_fit"
    if (
        (not fresh)
        and score >= settings["immediate_alert_score"]
        and settings["timestamp_policy"]["allow_unverified_current_jobs_in_digest"]
    ):
        return "high_priority_digest"
    return "silent"

def format_message(job: dict, evaluation: dict, bucket: str) -> tuple[str, str]:
    subject = f"{evaluation['classification']} — {evaluation['fit_score']}% — {job['title']}"
    body = f"""\
{bucket.replace('_', ' ').title()}

{job['title']}
{job['company']}
{job.get('location') or 'Location not supplied'}

Fit: {evaluation['fit_score']}/100 — {evaluation['classification']}
Recommendation: {evaluation['recommendation']}
Recommended resume: {evaluation['selected_resume']}
Freshness: {job.get('freshness_status')}

Why:
{evaluation['reasoning']}

Potential gaps:
{', '.join(evaluation.get('missing_requirements') or []) or 'None identified'}

Apply:
{job['apply_url']}
"""
    return subject, body

def console_notify(job: dict, evaluation: dict, bucket: str) -> None:
    if bucket == "silent":
        return
    subject, body = format_message(job, evaluation, bucket)
    print("\n" + "=" * 72)
    print(subject)
    print(body)
    print("=" * 72)

def email_notify(job: dict, evaluation: dict, bucket: str) -> tuple[bool, str]:
    if str(env("SMTP_ENABLED", "false")).lower() not in {"1", "true", "yes", "on"}:
        return False, "SMTP disabled"

    host = env("SMTP_HOST")
    port = int(env("SMTP_PORT", "587"))
    username = env("SMTP_USERNAME")
    password = env("SMTP_PASSWORD")
    to_addr = env("ALERT_EMAIL_TO")
    from_addr = env("ALERT_EMAIL_FROM") or username

    if not all([host, username, password, to_addr, from_addr]):
        return False, "SMTP settings incomplete"

    subject, body = format_message(job, evaluation, bucket)
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg.set_content(body)

    try:
        with smtplib.SMTP(host, port, timeout=30) as smtp:
            smtp.starttls()
            smtp.login(username, password)
            smtp.send_message(msg)
        return True, "sent"
    except Exception as exc:
        return False, str(exc)

def email_high_priority_digest(items: list[tuple[dict, dict]]) -> tuple[bool, str]:
    if not items:
        return False, "no pending digest items"

    if str(env("SMTP_ENABLED", "false")).lower() not in {"1", "true", "yes", "on"}:
        return False, "SMTP disabled"

    host = env("SMTP_HOST")
    port = int(env("SMTP_PORT", "587"))
    username = env("SMTP_USERNAME")
    password = env("SMTP_PASSWORD")
    to_addr = env("ALERT_EMAIL_TO")
    from_addr = env("ALERT_EMAIL_FROM") or username

    if not all([host, username, password, to_addr, from_addr]):
        return False, "SMTP settings incomplete"

    lines = [
        "High-Priority Daily Job Digest",
        "",
        f"These {len(items)} strong-fit job(s) had an unverified posting time and were held for the daily digest.",
        "",
    ]

    for index, (job, evaluation) in enumerate(items, start=1):
        lines.extend([
            f"{index}. {job['title']}",
            job["company"],
            job.get("location") or "Location not supplied",
            f"Fit: {evaluation['fit_score']}/100 — {evaluation['classification']}",
            f"Recommendation: {evaluation['recommendation']}",
            f"Apply: {job['apply_url']}",
            "",
        ])

    msg = EmailMessage()
    msg["Subject"] = f"High-Priority Job Digest — {len(items)} job(s)"
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg.set_content("\n".join(lines))

    try:
        with smtplib.SMTP(host, port, timeout=30) as smtp:
            smtp.starttls()
            smtp.login(username, password)
            smtp.send_message(msg)
        return True, "sent"
    except Exception as exc:
        return False, str(exc)
