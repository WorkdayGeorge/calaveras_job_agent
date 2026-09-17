from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from .config import env
from .db import SessionLocal, init_db
from .models import Evaluation, Job, Notification
from .notify import email_high_priority_digest
from .pipeline import job_to_dict
from .settings_store import get_int, get_setting


def send_digest_preview() -> dict:
    """Send a non-mutating test of the production daily digest."""
    init_db()

    with SessionLocal() as session:
        pending_rows = session.execute(
            select(Notification, Job, Evaluation)
            .join(Job, Notification.job_id == Job.id)
            .join(Evaluation, Notification.evaluation_id == Evaluation.id)
            .where(Notification.status == "pending_digest")
            .order_by(Evaluation.fit_score.desc(), Job.first_seen_at.desc())
        ).all()

        immediate_alert_score = get_int(session, "immediate_alert_score", 75)
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        recent_rows = session.execute(
            select(Job, Evaluation)
            .join(Evaluation, Evaluation.job_id == Job.id)
            .where(
                Evaluation.evaluated_at >= cutoff,
                Evaluation.fit_score >= immediate_alert_score,
            )
            .order_by(
                Evaluation.fit_score.desc(),
                Evaluation.evaluated_at.desc(),
            )
        ).all()

        pending_items = [
            (
                job_to_dict(job),
                {
                    "fit_score": evaluation.fit_score,
                    "classification": evaluation.classification,
                    "recommendation": evaluation.recommendation,
                },
            )
            for _, job, evaluation in pending_rows
        ]
        recent_items = [
            (
                job_to_dict(job),
                {
                    "fit_score": evaluation.fit_score,
                    "classification": evaluation.classification,
                    "recommendation": evaluation.recommendation,
                    "evaluated_at": evaluation.evaluated_at.isoformat(),
                },
            )
            for job, evaluation in recent_rows
        ]

        recipient = (
            get_setting(session, "alert_email_to", env("ALERT_EMAIL_TO", ""))
            or env("ALERT_EMAIL_TO", "")
        )
        sent, detail = email_high_priority_digest(
            pending_items,
            recipient=recipient,
            recent_immediate_items=recent_items,
            immediate_alert_score=immediate_alert_score,
            subject_prefix="[TEST] ",
            allow_empty=True,
        )

        result = {
            "status": "sent" if sent else "failed",
            "pending_count": len(pending_items),
            "recent_immediate_count": len(recent_items),
            "detail": detail,
        }
        print("Digest preview:", result)
        return result


if __name__ == "__main__":
    send_digest_preview()
