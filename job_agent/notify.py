\
from __future__ import annotations

import smtplib
import re
from email.message import EmailMessage
from datetime import datetime, timezone

from .config import env


def normalize_email_address(value: str | None) -> str | None:
    """Return a safe single recipient address, or None when invalid."""
    address = str(value or "").strip()
    if "\r" in address or "\n" in address:
        return None
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", address):
        return None
    return address

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

def email_notify(
    job: dict,
    evaluation: dict,
    bucket: str,
    recipient: str | None = None,
) -> tuple[bool, str]:
    if str(env("SMTP_ENABLED", "false")).lower() not in {"1", "true", "yes", "on"}:
        return False, "SMTP disabled"

    host = env("SMTP_HOST")
    port = int(env("SMTP_PORT", "587"))
    username = env("SMTP_USERNAME")
    password = env("SMTP_PASSWORD")
    to_addr = normalize_email_address(recipient or env("ALERT_EMAIL_TO"))
    from_addr = env("ALERT_EMAIL_FROM") or username

    if not all([host, username, password, to_addr, from_addr]):
        return False, "SMTP settings incomplete or alert recipient invalid"

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

def email_high_priority_digest(
    items: list[tuple[dict, dict]],
    recipient: str | None = None,
    recent_immediate_items: list[tuple[dict, dict]] | None = None,
    immediate_alert_score: int | None = None,
    subject_prefix: str = "",
    allow_empty: bool = False,
) -> tuple[bool, str]:
    recent_immediate_items = recent_immediate_items or []
    if not allow_empty and not items and not recent_immediate_items:
        return False, "no digest items"

    if str(env("SMTP_ENABLED", "false")).lower() not in {"1", "true", "yes", "on"}:
        return False, "SMTP disabled"

    host = env("SMTP_HOST")
    port = int(env("SMTP_PORT", "587"))
    username = env("SMTP_USERNAME")
    password = env("SMTP_PASSWORD")
    to_addr = normalize_email_address(recipient or env("ALERT_EMAIL_TO"))
    from_addr = env("ALERT_EMAIL_FROM") or username

    if not all([host, username, password, to_addr, from_addr]):
        return False, "SMTP settings incomplete or alert recipient invalid"

    lines = [
        "High-Priority Daily Job Digest",
        "",
        "Pending High-Priority Jobs",
        "",
        f"These {len(items)} strong-fit job(s) had an unverified posting time and were held for the daily digest.",
        "",
    ]

    if items:
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
    else:
        lines.extend(["No newly queued jobs for today's digest.", ""])

    threshold_text = (
        str(immediate_alert_score)
        if immediate_alert_score is not None
        else "the configured"
    )
    lines.extend([
        "Last 30 Days — Immediate Alert Threshold",
        "",
        f"These {len(recent_immediate_items)} job(s) evaluated in the last 30 days met or exceeded {threshold_text}/100.",
        "",
    ])

    if recent_immediate_items:
        for index, (job, evaluation) in enumerate(
            recent_immediate_items, start=1
        ):
            lines.extend([
                f"{index}. {job['title']}",
                job["company"],
                job.get("location") or "Location not supplied",
                f"Fit: {evaluation['fit_score']}/100 — {evaluation['classification']}",
                f"Recommendation: {evaluation['recommendation']}",
                f"Evaluated: {evaluation.get('evaluated_at') or 'Date unavailable'}",
                f"Apply: {job['apply_url']}",
                "",
            ])
    else:
        lines.extend(["No qualifying jobs in the last 30 days.", ""])

    msg = EmailMessage()
    msg["Subject"] = (
        f"{subject_prefix}High-Priority Job Digest — "
        f"{len(items)} new, {len(recent_immediate_items)} recent"
    )
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
