from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import and_, func, select

from .models import Evaluation, Job, Notification, RunLog, User, UserJobState

PACIFIC_TZ = ZoneInfo("America/Los_Angeles")


def resolve_date_range(
    period: str = "30d",
    start: str | None = None,
    end: str | None = None,
    now: datetime | None = None,
) -> tuple[datetime, datetime, str]:
    now_pt = (now or datetime.now(timezone.utc)).astimezone(PACIFIC_TZ)
    today = now_pt.date()
    if period == "today":
        start_date, end_date, label = today, today, "Today"
    elif period == "7d":
        start_date, end_date, label = today - timedelta(days=6), today, "Last 7 days"
    elif period == "month":
        start_date, end_date, label = today.replace(day=1), today, "This month"
    elif period == "custom" and start and end:
        try:
            start_date, end_date = date.fromisoformat(start), date.fromisoformat(end)
            if end_date < start_date:
                raise ValueError
            label = f"{start_date.isoformat()} through {end_date.isoformat()}"
        except ValueError:
            start_date, end_date, label = today - timedelta(days=29), today, "Last 30 days"
    else:
        start_date, end_date, label = today - timedelta(days=29), today, "Last 30 days"
    start_utc = datetime.combine(start_date, time.min, PACIFIC_TZ).astimezone(timezone.utc)
    end_utc = datetime.combine(end_date + timedelta(days=1), time.min, PACIFIC_TZ).astimezone(timezone.utc)
    return start_utc, end_utc, label


def _local_day(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(PACIFIC_TZ).strftime("%b %-d")


def build_admin_analytics(session, start_utc: datetime, end_utc: datetime) -> dict:
    users = session.scalars(select(User).order_by(User.display_name)).all()
    user_map = {user.id: user for user in users}
    notifications = session.execute(
        select(Notification, Job, Evaluation)
        .join(Job, Notification.job_id == Job.id)
        .join(Evaluation, Notification.evaluation_id == Evaluation.id)
        .where(Notification.sent_at >= start_utc, Notification.sent_at < end_utc)
        .order_by(Notification.sent_at.desc())
    ).all()
    states = session.execute(
        select(UserJobState, Job)
        .join(Job, UserJobState.job_id == Job.id)
        .where(UserJobState.updated_at >= start_utc, UserJobState.updated_at < end_utc)
        .order_by(UserJobState.updated_at.desc())
    ).all()
    evaluations = session.execute(
        select(Evaluation, Job)
        .join(Job, Evaluation.job_id == Job.id)
        .where(Evaluation.evaluated_at >= start_utc, Evaluation.evaluated_at < end_utc)
    ).all()
    runs = session.scalars(
        select(RunLog).where(
            RunLog.started_at >= start_utc,
            RunLog.started_at < end_utc,
        )
    ).all()

    delivered = [row for row in notifications if row[0].status == "sent"]
    failed = [row for row in notifications if row[0].status in {"failed", "not_sent"}]
    applications = [row for row in states if row[0].applied_at and start_utc <= _aware(row[0].applied_at) < end_utc]
    interviews = [row for row in states if row[0].interview_at and start_utc <= _aware(row[0].interview_at) < end_utc]
    hired = [row for row in states if row[0].status == "hired"]

    start_day = start_utc.astimezone(PACIFIC_TZ).date()
    end_day = (end_utc - timedelta(microseconds=1)).astimezone(PACIFIC_TZ).date()
    day_counts = defaultdict(lambda: {"notifications": 0, "applications": 0})
    cursor = start_day
    while cursor <= end_day:
        day_counts[cursor.strftime("%b %-d")]
        cursor += timedelta(days=1)
    for notification, _, _ in delivered:
        day_counts[_local_day(notification.sent_at)]["notifications"] += 1
    for state, _ in applications:
        day_counts[_local_day(state.applied_at)]["applications"] += 1

    source_rows = defaultdict(lambda: {"evaluated": 0, "strong": 0, "notified": 0, "applied": 0})
    for evaluation, job in evaluations:
        source = job.source or "Unknown"
        source_rows[source]["evaluated"] += 1
        if evaluation.fit_score >= 75:
            source_rows[source]["strong"] += 1
    for _, job, _ in delivered:
        source_rows[job.source or "Unknown"]["notified"] += 1
    for _, job in applications:
        source_rows[job.source or "Unknown"]["applied"] += 1

    per_user = defaultdict(lambda: {"notifications": 0, "applications": 0, "interviews": 0})
    for notification, _, _ in delivered:
        per_user[notification.user_id]["notifications"] += 1
    for state, _ in applications:
        per_user[state.user_id]["applications"] += 1
    for state, _ in interviews:
        per_user[state.user_id]["interviews"] += 1

    user_rows = []
    for user in users:
        user_rows.append({
            "user": user,
            **per_user[user.id],
        })

    notification_rows = [{
        "notification": notification,
        "job": job,
        "evaluation": evaluation,
        "user": user_map.get(notification.user_id),
    } for notification, job, evaluation in notifications]
    application_rows = [{
        "state": state,
        "job": job,
        "user": user_map.get(state.user_id),
    } for state, job in states if state.applied_at]

    trend = [{"day": day, **values} for day, values in day_counts.items()]
    funnel = [
        {"label": "Notified", "count": len(delivered)},
        {"label": "Interested", "count": sum(state.status == "interested" for state, _ in states)},
        {"label": "Applied", "count": len(applications)},
        {"label": "Interview", "count": len(interviews)},
        {"label": "Hired", "count": len(hired)},
    ]
    source_list = [
        {"source": source, **values}
        for source, values in sorted(
            source_rows.items(),
            key=lambda item: (-item[1]["notified"], -item[1]["evaluated"], item[0]),
        )
    ]
    return {
        "metrics": {
            "active_users": sum(user.status == "active" for user in users),
            "jobs_evaluated": len(evaluations),
            "notifications_sent": len(delivered),
            "notification_failures": len(failed),
            "applications": len(applications),
            "interviews": len(interviews),
            "hires": len(hired),
            "run_failures": sum(run.status in {"partial", "error"} for run in runs),
        },
        "trend": trend,
        "funnel": funnel,
        "sources": source_list,
        "maxima": {
            "trend": max(1, max([max(row["notifications"], row["applications"]) for row in trend] or [1])),
            "funnel": max(1, max([row["count"] for row in funnel] or [1])),
            "source": max(1, max([max(row["notified"], row["applied"]) for row in source_list] or [1])),
        },
        "users": user_rows,
        "notifications": notification_rows,
        "applications": application_rows,
    }


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
