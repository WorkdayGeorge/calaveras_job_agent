\
from __future__ import annotations

import os
import json
import secrets
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from pathlib import Path

from fastapi import FastAPI, Request, Form, UploadFile, File, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy import select, desc, func, and_

from job_agent.db import init_db, SessionLocal
from job_agent.models import (
    Job, Evaluation, SearchTerm, RunLog, ResumeAsset, ApplicationPackage,
    User, UserJobState, CandidateProfile, UserPreference,
)
from job_agent.application_builder import build_application_materials
from job_agent.source_catalog import get_job_sources
from job_agent.config import load_settings, env
from job_agent.notify import email_notify, email_text, normalize_email_address
from job_agent.settings_store import (
    seed_settings, get_bool, get_int, get_setting, set_setting
)
from job_agent.user_data import assign_legacy_records_to_admin, get_or_create_job_state
from job_agent.profile_store import (
    ensure_user_profile_records,
    seed_admin_profile,
    validate_candidate_profile,
)




from .cloud_trigger import trigger_worker
from .resume_storage import save_resume
from .auth import (
    bootstrap_admin,
    consume_token,
    database_auth_enabled,
    find_user_by_email,
    hash_password,
    issue_token,
    new_numeric_code,
    normalize_login_email,
    record_audit,
    token_digest,
    utc_aware,
    verify_password,
)

BASE_DIR = Path(__file__).resolve().parents[1]
templates = Jinja2Templates(directory=str(BASE_DIR / "web" / "templates"))

PACIFIC_TZ = ZoneInfo("America/Los_Angeles")

def pacific_time(value):
    """Format a database timestamp for display in Pacific Time."""
    if value is None:
        return ""

    # Some database drivers may return a naive datetime.
    # Our stored timestamps are UTC, so assume UTC when tzinfo is absent.
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)

    local = value.astimezone(PACIFIC_TZ)

    return (
        f"{local.strftime('%b')} {local.day}, {local.year} "
        f"{local.strftime('%I:%M %p').lstrip('0')} "
        f"{local.tzname()}"
    )

templates.env.filters["pacific_time"] = pacific_time

def pacific_datetime_input(value):
    if value is None:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(PACIFIC_TZ).strftime("%Y-%m-%dT%H:%M")

templates.env.filters["pacific_datetime_input"] = pacific_datetime_input

def parse_pacific_datetime(value: str | None):
    if not value:
        return None
    try:
        local = datetime.fromisoformat(value)
        return local.replace(tzinfo=PACIFIC_TZ).astimezone(timezone.utc)
    except ValueError:
        return None

def job_sort_order(sort_by):
    """Return SQLAlchemy ORDER BY expressions for job listings."""
    if sort_by == "oldest_posted":
        return (
            Job.posted_at.is_(None),
            Job.posted_at.asc(),
            Job.first_seen_at.desc(),
        )
    if sort_by == "newest_found":
        return (Job.first_seen_at.desc(),)
    if sort_by == "highest_fit":
        return (
            Evaluation.fit_score.desc().nullslast(),
            Job.posted_at.desc().nullslast(),
        )
    if sort_by == "lowest_fit":
        return (
            Evaluation.fit_score.asc().nullslast(),
            Job.posted_at.desc().nullslast(),
        )
    if sort_by == "title":
        return (Job.title.asc(),)
    if sort_by == "company":
        return (Job.company.asc(),)

    # Default: newest verified posting first.
    # Jobs without a verified posting time appear afterward.
    return (
        Job.posted_at.is_(None),
        Job.posted_at.desc(),
        Job.first_seen_at.desc(),
    )

app = FastAPI(title="Calaveras Job Agent")
app.add_middleware(
    SessionMiddleware,
    secret_key=env("SESSION_SECRET", "dev-only-change-me"),
    https_only=(env("APP_ENV", "development") == "production"),
    same_site="lax",
)

def authed(request: Request) -> bool:
    return bool(request.session.get("user_id") or request.session.get("authenticated"))

def admin_user(request: Request) -> bool:
    return authed(request) and request.session.get("role", "administrator") == "administrator"

def current_user_id(request: Request) -> str | None:
    return request.session.get("user_id")

def owner_clause(column, request: Request):
    user_id = current_user_id(request)
    return column == user_id if user_id else column.is_(None)

def current_resume_version(session, request: Request) -> str:
    user_id = current_user_id(request)
    profile = session.get(CandidateProfile, user_id) if user_id else None
    return profile.resume_version if profile else "master-profile-v1"

def require_auth(request: Request):
    if not authed(request):
        return RedirectResponse("/login", status_code=303)
    if request.session.get("must_change_password") and request.url.path != "/account/change-password":
        return RedirectResponse("/account/change-password", status_code=303)
    return None

def require_admin(request: Request):
    denial = require_auth(request)
    if denial:
        return denial
    if not admin_user(request):
        return HTMLResponse("Administrator access required", status_code=403)
    return None

@app.on_event("startup")
def startup():
    init_db()
    with SessionLocal() as session:
        seed_settings(session, load_settings())
        admin = bootstrap_admin(session)
        assign_legacy_records_to_admin(session, admin)
        seed_admin_profile(
            session,
            admin,
            get_setting(session, "alert_email_to", env("ALERT_EMAIL_TO", "")),
        )

@app.get("/health")
def health():
    return {"ok": True}

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse(
        request,
        "login.html",
        {"error": None, "database_auth": database_auth_enabled()}
    )

@app.post("/login", response_class=HTMLResponse)
def login(request: Request, password: str = Form(...), email: str = Form("")):
    if database_auth_enabled():
        now = datetime.now(timezone.utc)
        with SessionLocal() as session:
            user = find_user_by_email(session, email)
            if (
                not user
                or user.status != "active"
                or (user.locked_until and utc_aware(user.locked_until) > now)
                or not verify_password(password, user.password_hash)
            ):
                if user and user.status == "active":
                    user.failed_login_attempts += 1
                    if user.failed_login_attempts >= 5:
                        user.locked_until = now + timedelta(minutes=15)
                        user.failed_login_attempts = 0
                    session.commit()
                return templates.TemplateResponse(
                    request,
                    "login.html",
                    {"error": "Invalid email or password.", "database_auth": True},
                    status_code=401,
                )

            code = new_numeric_code()
            issue_token(session, user, "login_otp", code, minutes=10)
            sent, _ = email_text(
                user.email,
                "Your Calaveras Job Agent sign-in code",
                f"Your six-digit sign-in code is: {code}\n\nThis code expires in 10 minutes.",
            )
            if not sent:
                record_audit(session, "login_otp_delivery_failed", target_user_id=user.id, request=request)
                return templates.TemplateResponse(
                    request,
                    "login.html",
                    {"error": "The sign-in code could not be sent. Please contact the administrator.", "database_auth": True},
                    status_code=503,
                )
            request.session.clear()
            request.session["pending_user_id"] = user.id
            return RedirectResponse("/login/verify", status_code=303)

    configured = env("ADMIN_PASSWORD", "")
    if configured and secrets.compare_digest(password, configured):
        with SessionLocal() as session:
            admin = bootstrap_admin(session)
            assign_legacy_records_to_admin(session, admin)
        request.session["authenticated"] = True
        request.session["role"] = "administrator"
        if admin:
            request.session["user_id"] = admin.id
            request.session["email"] = admin.email
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(
        request,
        "login.html",
        {"error": "Invalid password.", "database_auth": False},
        status_code=401
    )

@app.get("/login/verify", response_class=HTMLResponse)
def verify_login_page(request: Request):
    if not request.session.get("pending_user_id"):
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse(request, "verify_login.html", {"error": None})

@app.post("/login/verify", response_class=HTMLResponse)
def verify_login(request: Request, code: str = Form(...)):
    pending_user_id = request.session.get("pending_user_id")
    with SessionLocal() as session:
        user = session.get(User, pending_user_id) if pending_user_id else None
        if not user or not consume_token(session, user, "login_otp", code):
            return templates.TemplateResponse(
                request, "verify_login.html", {"error": "Invalid or expired code."}, status_code=401
            )
        now = datetime.now(timezone.utc)
        user.failed_login_attempts = 0
        user.locked_until = None
        user.last_login_at = now
        user.updated_at = now
        session.commit()
        record_audit(session, "login_succeeded", actor_user_id=user.id, request=request)
        request.session.clear()
        request.session.update({
            "user_id": user.id,
            "role": user.role,
            "email": user.email,
            "must_change_password": user.must_change_password,
        })
        destination = "/account/change-password" if user.must_change_password else "/"
        return RedirectResponse(destination, status_code=303)

@app.get("/account/change-password", response_class=HTMLResponse)
def change_password_page(request: Request):
    denial = require_auth(request)
    if denial:
        return denial
    return templates.TemplateResponse(request, "change_password.html", {"error": None})

@app.post("/account/change-password", response_class=HTMLResponse)
def change_password(request: Request, current_password: str = Form(...), new_password: str = Form(...), confirm_password: str = Form(...)):
    denial = require_auth(request)
    if denial:
        return denial
    if not database_auth_enabled():
        return RedirectResponse("/", status_code=303)
    with SessionLocal() as session:
        user = session.get(User, request.session.get("user_id"))
        error = None
        if not user or not verify_password(current_password, user.password_hash):
            error = "Current password is incorrect."
        elif new_password != confirm_password:
            error = "New passwords do not match."
        else:
            try:
                user.password_hash = hash_password(new_password)
            except ValueError as exc:
                error = str(exc)
        if error:
            return templates.TemplateResponse(request, "change_password.html", {"error": error}, status_code=400)
        user.must_change_password = False
        user.updated_at = datetime.now(timezone.utc)
        session.commit()
        record_audit(session, "password_changed", actor_user_id=user.id, target_user_id=user.id, request=request)
        request.session["must_change_password"] = False
    return RedirectResponse("/", status_code=303)

@app.get("/forgot-password", response_class=HTMLResponse)
def forgot_password_page(request: Request):
    return templates.TemplateResponse(request, "forgot_password.html", {"message": None})

@app.post("/forgot-password", response_class=HTMLResponse)
def forgot_password(request: Request, email: str = Form(...)):
    generic = "If an active account exists, a reset link has been sent."
    if database_auth_enabled():
        with SessionLocal() as session:
            user = find_user_by_email(session, email)
            if user and user.status == "active":
                raw_token = secrets.token_urlsafe(32)
                issue_token(session, user, "password_reset", raw_token, minutes=30)
                reset_url = str(request.url_for("reset_password_page")) + f"?token={raw_token}"
                email_text(user.email, "Reset your Calaveras Job Agent password", f"Use this link within 30 minutes to reset your password:\n\n{reset_url}")
                record_audit(session, "password_reset_requested", target_user_id=user.id, request=request)
    return templates.TemplateResponse(request, "forgot_password.html", {"message": generic})

@app.get("/reset-password", response_class=HTMLResponse)
def reset_password_page(request: Request, token: str = ""):
    return templates.TemplateResponse(request, "reset_password.html", {"token": token, "error": None})

@app.post("/reset-password", response_class=HTMLResponse)
def reset_password(request: Request, token: str = Form(...), new_password: str = Form(...), confirm_password: str = Form(...)):
    error = None
    if new_password != confirm_password:
        error = "New passwords do not match."
    with SessionLocal() as session:
        from job_agent.models import AuthToken
        token_row = session.scalar(select(AuthToken).where(AuthToken.token_hash == token_digest(token), AuthToken.purpose == "password_reset", AuthToken.used_at.is_(None)))
        user = session.get(User, token_row.user_id) if token_row else None
        if not error and (not user or not consume_token(session, user, "password_reset", token)):
            error = "This reset link is invalid or expired."
        if not error:
            try:
                user.password_hash = hash_password(new_password)
            except ValueError as exc:
                error = str(exc)
        if error:
            return templates.TemplateResponse(request, "reset_password.html", {"token": token, "error": error}, status_code=400)
        user.must_change_password = False
        user.failed_login_attempts = 0
        user.locked_until = None
        user.updated_at = datetime.now(timezone.utc)
        session.commit()
        record_audit(session, "password_reset_completed", target_user_id=user.id, request=request)
    return RedirectResponse("/login?message=Password+reset", status_code=303)

@app.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)

@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, sort: str = "newest_posted"):
    denial = require_auth(request)
    if denial:
        return denial

    with SessionLocal() as session:
        resume_version = current_resume_version(session, request)
        enabled = get_bool(session, "agent_enabled", True)
        latest_run = session.scalar(select(RunLog).order_by(desc(RunLog.started_at)).limit(1))
        total_jobs = session.scalar(select(func.count(Job.id))) or 0
        strong = session.scalar(
            select(func.count(Evaluation.id)).where(
                owner_clause(Evaluation.user_id, request),
                Evaluation.resume_version == resume_version,
                Evaluation.fit_score >= 75,
            )
        ) or 0
        recent = session.execute(
            select(Job, Evaluation, UserJobState)
            .join(
                Evaluation,
                and_(
                    Evaluation.job_id == Job.id,
                    owner_clause(Evaluation.user_id, request),
                    Evaluation.resume_version == resume_version,
                ),
                isouter=True,
            )
            .join(
                UserJobState,
                and_(
                    UserJobState.job_id == Job.id,
                    UserJobState.user_id == current_user_id(request),
                ),
                isouter=True,
            )
            .order_by(*job_sort_order(sort))
            .limit(8)
        ).all()

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "enabled": enabled,
            "latest_run": latest_run,
            "total_jobs": total_jobs,
            "strong": strong,
            "recent": recent,
            "sort_by": sort,
        }
    )

@app.post("/admin/toggle")
def toggle_agent(request: Request):
    denial = require_admin(request)
    if denial:
        return denial
    with SessionLocal() as session:
        current = get_bool(session, "agent_enabled", True)
        set_setting(session, "agent_enabled", "false" if current else "true")
    return RedirectResponse("/", status_code=303)

@app.post("/admin/run-now")
def run_now(request: Request, background_tasks: BackgroundTasks):
    denial = require_admin(request)
    if denial:
        return denial
    background_tasks.add_task(trigger_worker)
    return RedirectResponse("/?message=Run+requested", status_code=303)

@app.post("/admin/test-email")
def test_email(request: Request):
    denial = require_admin(request)
    if denial:
        return denial

    test_job = {
        "title": "Email Notification Test",
        "company": "Calaveras Job Agent",
        "location": "Calaveras County, CA",
        "freshness_status": "verified_fresh",
        "apply_url": "https://example.com",
    }

    test_evaluation = {
        "fit_score": 100,
        "classification": "Test Alert",
        "recommendation": "Email system is working",
        "selected_resume": "focused",
        "reasoning": "This is a test of the Calaveras Job Agent email notification system.",
        "missing_requirements": [],
    }

    with SessionLocal() as session:
        recipient = (
            get_setting(
                session,
                "alert_email_to",
                env("ALERT_EMAIL_TO", ""),
            )
            or env("ALERT_EMAIL_TO", "")
        )

    sent, result = email_notify(
        test_job,
        test_evaluation,
        "test",
        recipient=recipient,
    )

    if sent:
        return RedirectResponse("/?message=Test+email+sent", status_code=303)

    return RedirectResponse(
        f"/?message=Test+email+failed:+{result}",
        status_code=303,
    )


@app.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request):
    denial = require_admin(request)
    if denial:
        return denial
    with SessionLocal() as session:
        terms = session.scalars(select(SearchTerm).order_by(SearchTerm.term)).all()
        values = {
            "fresh_job_window_minutes": get_int(session, "fresh_job_window_minutes", 60),
            "minimum_fit_score": get_int(session, "minimum_fit_score", 60),
            "immediate_alert_score": get_int(session, "immediate_alert_score", 75),
            "allow_unverified_current_jobs_in_digest": get_bool(
                 session, "allow_unverified_current_jobs_in_digest", True
            ),
            "schedule_interval_minutes": get_int(
                 session, "schedule_interval_minutes", 15
            ),
            "schedule_start_time": get_setting(
                 session, "schedule_start_time", "09:00"
            ),
            "schedule_stop_time": get_setting(
                 session, "schedule_stop_time", "17:00"
            ),
            "high_priority_digest_time": get_setting(
                 session, "high_priority_digest_time", "17:05"
            ),
            "schedule_days": {
                 int(day)
                 for day in (
                     get_setting(session, "schedule_days", "0,1,2,3,4") or ""
                 ).split(",")
                 if day.strip().isdigit()
            },
            "alert_email_to": (
                get_setting(
                    session,
                    "alert_email_to",
                    env("ALERT_EMAIL_TO", ""),
                )
                or env("ALERT_EMAIL_TO", "")
            ),
        }
    return templates.TemplateResponse(
        request,
        "settings.html",
        {"terms": terms, "values": values}
    )

@app.post("/settings")
def save_settings(
    request: Request,
    fresh_job_window_minutes: int = Form(...),
    minimum_fit_score: int = Form(...),
    immediate_alert_score: int = Form(...),
    schedule_interval_minutes: int = Form(...),
    schedule_start_time: str = Form(...),
    schedule_stop_time: str = Form(...),
    high_priority_digest_time: str = Form(...),
    schedule_days: list[str] = Form([]),
    allow_unverified_current_jobs_in_digest: str | None = Form(None),
    alert_email_to: str = Form(""),
):
    denial = require_admin(request)
    if denial:
        return denial
    recipient_input = alert_email_to.strip()
    validated_recipient = (
        normalize_email_address(recipient_input)
        if recipient_input
        else ""
    )
    if recipient_input and not validated_recipient:
        return RedirectResponse(
            "/settings?message=Enter+a+valid+single+email+address",
            status_code=303,
        )
    with SessionLocal() as session:
        set_setting(session, "alert_email_to", validated_recipient)
        set_setting(
            session,
            "fresh_job_window_minutes",
            str(max(1, fresh_job_window_minutes)),
        )
        set_setting(
            session,
            "minimum_fit_score",
            str(max(0, min(100, minimum_fit_score))),
        )
        set_setting(
            session,
            "immediate_alert_score",
            str(max(0, min(100, immediate_alert_score))),
        )

        allowed_intervals = {5, 10, 15, 30, 60}
        if schedule_interval_minutes not in allowed_intervals:
            schedule_interval_minutes = 15

        try:
            datetime.strptime(schedule_start_time, "%H:%M")
        except ValueError:
            schedule_start_time = "09:00"

        try:
            datetime.strptime(schedule_stop_time, "%H:%M")
        except ValueError:
            schedule_stop_time = "17:00"

        try:
            datetime.strptime(high_priority_digest_time, "%H:%M")
        except ValueError:
            high_priority_digest_time = "17:05"

        set_setting(
            session,
            "high_priority_digest_time",
            high_priority_digest_time,
        )

        valid_days = sorted({
            int(day)
            for day in schedule_days
            if day.isdigit() and 0 <= int(day) <= 6
        })

        set_setting(
            session,
            "schedule_interval_minutes",
            str(schedule_interval_minutes),
        )
        set_setting(
            session,
            "schedule_start_time",
            schedule_start_time,
        )
        set_setting(
            session,
            "schedule_stop_time",
            schedule_stop_time,
        )
        set_setting(
            session,
            "schedule_days",
            ",".join(str(day) for day in valid_days),
        )

        set_setting(
            session,
            "allow_unverified_current_jobs_in_digest",
            "true" if allow_unverified_current_jobs_in_digest else "false",
        )
    return RedirectResponse(
        "/settings?message=Settings+saved",
        status_code=303,
    )

@app.post("/settings/search-terms/add")
def add_term(request: Request, term: str = Form(...)):
    denial = require_admin(request)
    if denial:
        return denial
    term = " ".join(term.split()).strip()
    if term:
        with SessionLocal() as session:
            exists = session.scalar(select(SearchTerm).where(SearchTerm.term == term))
            if not exists:
                session.add(SearchTerm(
                    term=term, enabled=True, created_at=datetime.now(timezone.utc)
                ))
                session.commit()
    return RedirectResponse("/settings", status_code=303)

@app.post("/settings/search-terms/{term_id}/toggle")
def toggle_term(term_id: str, request: Request):
    denial = require_admin(request)
    if denial:
        return denial
    with SessionLocal() as session:
        obj = session.get(SearchTerm, term_id)
        if obj:
            obj.enabled = not obj.enabled
            session.commit()
    return RedirectResponse("/settings", status_code=303)

@app.post("/settings/search-terms/{term_id}/delete")
def delete_term(term_id: str, request: Request):
    denial = require_admin(request)
    if denial:
        return denial
    with SessionLocal() as session:
        obj = session.get(SearchTerm, term_id)
        if obj:
            session.delete(obj)
            session.commit()
    return RedirectResponse("/settings", status_code=303)

@app.get("/jobs", response_class=HTMLResponse)
def jobs_page(
    request: Request,
    status: str | None = None,
    sort: str = "newest_posted",
):
    denial = require_auth(request)
    if denial:
        return denial
    with SessionLocal() as session:
        resume_version = current_resume_version(session, request)
        stmt = (
            select(Job, Evaluation, UserJobState)
            .join(
                Evaluation,
                and_(
                    Evaluation.job_id == Job.id,
                    owner_clause(Evaluation.user_id, request),
                    Evaluation.resume_version == resume_version,
                ),
                isouter=True,
            )
            .join(
                UserJobState,
                and_(
                    UserJobState.job_id == Job.id,
                    UserJobState.user_id == current_user_id(request),
                ),
                isouter=True,
            )
            .order_by(*job_sort_order(sort))
        )
        if status:
            if current_user_id(request):
                stmt = stmt.where(UserJobState.status == status)
            else:
                stmt = stmt.where(Job.status == status)
        rows = session.execute(stmt.limit(250)).all()
    return templates.TemplateResponse(
        request,
        "jobs.html",
        {"rows": rows, "status_filter": status, "sort_by": sort}
    )

@app.post("/jobs/{job_id}/status")
def set_job_status(job_id: str, request: Request, status: str = Form(...)):
    denial = require_auth(request)
    if denial:
        return denial
    allowed = {"new", "reviewed", "interested", "applied", "interview", "rejected", "hired", "ignore", "expired"}
    if status not in allowed:
        return JSONResponse({"error": "invalid status"}, status_code=400)
    with SessionLocal() as session:
        job = session.get(Job, job_id)
        if job:
            user_id = current_user_id(request)
            if user_id:
                state = get_or_create_job_state(session, user_id, job)
                state.status = status
                state.updated_at = datetime.now(timezone.utc)
                if status == "applied" and not state.applied_at:
                    state.applied_at = datetime.now(timezone.utc)
            else:
                job.status = status
            session.commit()
    return RedirectResponse("/jobs", status_code=303)

@app.get("/jobs/{job_id}/application", response_class=HTMLResponse)
def application_page(job_id: str, request: Request):
    denial = require_auth(request)
    if denial:
        return denial

    with SessionLocal() as session:
        job = session.get(Job, job_id)
        if not job:
            return HTMLResponse("Job not found", status_code=404)

        package = session.scalar(
            select(ApplicationPackage)
            .where(
                ApplicationPackage.job_id == job_id,
                owner_clause(ApplicationPackage.user_id, request),
                ApplicationPackage.candidate_profile_version
                == current_resume_version(session, request),
            )
            .order_by(desc(ApplicationPackage.version))
            .limit(1)
        )
        state = session.scalar(
            select(UserJobState).where(
                UserJobState.user_id == current_user_id(request),
                UserJobState.job_id == job_id,
            )
        ) if current_user_id(request) else None

    return templates.TemplateResponse(
        request,
        "application.html",
        {"job": job, "package": package, "state": state}
    )


@app.post("/jobs/{job_id}/application-status")
def save_application_status(
    job_id: str,
    request: Request,
    status: str = Form(...),
    notes: str = Form(""),
    applied_at: str = Form(""),
    follow_up_at: str = Form(""),
    interview_at: str = Form(""),
    outcome: str = Form(""),
    application_url: str = Form(""),
):
    denial = require_auth(request)
    if denial:
        return denial
    user_id = current_user_id(request)
    if not user_id:
        return HTMLResponse("Account ownership is required", status_code=409)
    allowed = {"new", "reviewed", "interested", "applied", "interview", "rejected", "hired", "ignore", "expired"}
    if status not in allowed:
        return JSONResponse({"error": "invalid status"}, status_code=400)
    with SessionLocal() as session:
        job = session.get(Job, job_id)
        if not job:
            return HTMLResponse("Job not found", status_code=404)
        state = get_or_create_job_state(session, user_id, job)
        state.status = status
        state.notes = notes.strip() or None
        state.applied_at = parse_pacific_datetime(applied_at)
        state.follow_up_at = parse_pacific_datetime(follow_up_at)
        state.interview_at = parse_pacific_datetime(interview_at)
        state.outcome = outcome.strip() or None
        state.application_url = application_url.strip() or job.apply_url
        state.updated_at = datetime.now(timezone.utc)
        if status == "applied" and not state.applied_at:
            state.applied_at = datetime.now(timezone.utc)
        session.commit()
    return RedirectResponse(f"/jobs/{job_id}/application", status_code=303)



@app.post("/jobs/{job_id}/application/build")
def build_application_package(job_id: str, request: Request):
    denial = require_auth(request)
    if denial:
        return denial

    with SessionLocal() as session:
        job = session.get(Job, job_id)
        if not job:
            return HTMLResponse("Job not found", status_code=404)

        candidate_profile = session.get(
            CandidateProfile,
            current_user_id(request),
        ) if current_user_id(request) else None
        if not candidate_profile or not candidate_profile.is_active:
            return HTMLResponse(
                "An active administrator-approved candidate profile is required.",
                status_code=409,
            )

        job_data = {
            "title": job.title,
            "company": job.company,
            "location": job.location,
            "employment_type": job.employment_type,
            "description": job.description,
            "requirements": job.requirements or [],
            "source": job.source,
        }

        try:
            result = build_application_materials(
                job_data,
                profile=candidate_profile.profile_data,
            )
        except Exception:
            return HTMLResponse(
                "Application package generation failed. Please try again.",
                status_code=500,
            )

        current_version = session.scalar(
            select(func.max(ApplicationPackage.version))
            .where(
                ApplicationPackage.job_id == job_id,
                owner_clause(ApplicationPackage.user_id, request),
            )
        ) or 0

        now = datetime.now(timezone.utc)
        package = ApplicationPackage(
            user_id=current_user_id(request),
            candidate_profile_version=candidate_profile.resume_version,
            job_id=job_id,
            version=current_version + 1,
            tailored_resume=result["tailored_resume"],
            cover_letter=result["cover_letter"],
            interview_questions=result["interview_questions"],
            job_description_snapshot=job.description,
            generation_model=env("OPENAI_MODEL", "gpt-5.6-luna"),
            truth_check_notes=result["truth_check_notes"],
            created_at=now,
            updated_at=now,
        )
        session.add(package)
        session.commit()

    return RedirectResponse(
        f"/jobs/{job_id}/application",
        status_code=303,
    )


@app.get("/admin/users", response_class=HTMLResponse)
def users_page(request: Request):
    denial = require_admin(request)
    if denial:
        return denial
    with SessionLocal() as session:
        users = session.scalars(select(User).order_by(User.created_at.desc())).all()
    return templates.TemplateResponse(request, "users.html", {"users": users})


@app.post("/admin/users")
def create_user(
    request: Request,
    email: str = Form(...),
    display_name: str = Form(...),
    temporary_password: str = Form(...),
):
    denial = require_admin(request)
    if denial:
        return denial
    normalized_email = normalize_login_email(email)
    if not normalized_email:
        return RedirectResponse("/admin/users?message=Enter+a+valid+email", status_code=303)
    try:
        password_hash = hash_password(temporary_password)
    except ValueError:
        return RedirectResponse("/admin/users?message=Temporary+password+must+be+at+least+12+characters", status_code=303)
    with SessionLocal() as session:
        if find_user_by_email(session, normalized_email):
            return RedirectResponse("/admin/users?message=That+email+already+exists", status_code=303)
        now = datetime.now(timezone.utc)
        user = User(
            email=normalized_email,
            display_name=display_name.strip() or normalized_email,
            password_hash=password_hash,
            role="user",
            status="active",
            must_change_password=True,
            created_at=now,
            updated_at=now,
        )
        session.add(user)
        session.commit()
        ensure_user_profile_records(session, user)
        record_audit(
            session,
            "user_created",
            actor_user_id=request.session.get("user_id"),
            target_user_id=user.id,
            request=request,
        )
    return RedirectResponse("/admin/users?message=User+created", status_code=303)


@app.post("/admin/users/{user_id}/status")
def change_user_status(user_id: str, request: Request, status: str = Form(...)):
    denial = require_admin(request)
    if denial:
        return denial
    if status not in {"active", "suspended", "archived"}:
        return JSONResponse({"error": "invalid status"}, status_code=400)
    if user_id == request.session.get("user_id") and status != "active":
        return RedirectResponse("/admin/users?message=You+cannot+suspend+your+own+account", status_code=303)
    with SessionLocal() as session:
        user = session.get(User, user_id)
        if user:
            user.status = status
            user.updated_at = datetime.now(timezone.utc)
            session.commit()
            record_audit(
                session,
                "user_status_changed",
                actor_user_id=request.session.get("user_id"),
                target_user_id=user.id,
                request=request,
                detail={"status": status},
            )
    return RedirectResponse("/admin/users", status_code=303)


@app.get("/admin/users/{user_id}/profile", response_class=HTMLResponse)
def user_profile_page(user_id: str, request: Request):
    denial = require_admin(request)
    if denial:
        return denial
    with SessionLocal() as session:
        user = session.get(User, user_id)
        if not user:
            return HTMLResponse("User not found", status_code=404)
        profile, preference = ensure_user_profile_records(session, user)
        profile_json = json.dumps(profile.profile_data, indent=2, ensure_ascii=False)
    return templates.TemplateResponse(request, "user_profile.html", {
        "user": user,
        "profile": profile,
        "preference": preference,
        "profile_json": profile_json,
        "error": None,
    })


@app.post("/admin/users/{user_id}/profile", response_class=HTMLResponse)
def save_user_profile(
    user_id: str,
    request: Request,
    profile_json: str = Form(...),
    notification_email: str = Form(...),
    digest_time: str = Form("17:05"),
    is_active: str | None = Form(None),
    immediate_alerts: str | None = Form(None),
    daily_digest: str | None = Form(None),
):
    denial = require_admin(request)
    if denial:
        return denial
    try:
        profile_data = json.loads(profile_json)
    except json.JSONDecodeError as exc:
        profile_data = None
        errors = [f"Profile JSON is invalid near line {exc.lineno}: {exc.msg}"]
    else:
        errors = validate_candidate_profile(profile_data)
    recipient = normalize_email_address(notification_email)
    if not recipient:
        errors.append("Notification email must be a valid single email address.")
    try:
        datetime.strptime(digest_time, "%H:%M")
    except ValueError:
        errors.append("Digest time must be a valid time.")

    with SessionLocal() as session:
        user = session.get(User, user_id)
        if not user:
            return HTMLResponse("User not found", status_code=404)
        profile, preference = ensure_user_profile_records(session, user)
        if errors:
            return templates.TemplateResponse(request, "user_profile.html", {
                "user": user,
                "profile": profile,
                "preference": preference,
                "profile_json": profile_json,
                "error": " ".join(errors),
            }, status_code=400)

        if profile.profile_data != profile_data:
            profile.version += 1
            profile.resume_version = f"profile-v{profile.version}"
            profile.profile_data = profile_data
        profile.is_active = bool(is_active)
        profile.updated_at = datetime.now(timezone.utc)
        preference.notification_email = recipient
        preference.digest_time = digest_time
        preference.immediate_alerts = bool(immediate_alerts)
        preference.daily_digest = bool(daily_digest)
        preference.updated_at = datetime.now(timezone.utc)
        session.commit()
        record_audit(
            session,
            "candidate_profile_updated",
            actor_user_id=current_user_id(request),
            target_user_id=user.id,
            request=request,
            detail={"active": profile.is_active, "version": profile.version},
        )
    return RedirectResponse(
        f"/admin/users/{user_id}/profile?message=Profile+saved",
        status_code=303,
    )


@app.get("/sources", response_class=HTMLResponse)
def sources_page(request: Request):
    denial = require_admin(request)
    if denial:
        return denial

    sources = get_job_sources()
    return templates.TemplateResponse(
        request,
        "sources.html",
        {"sources": sources},
    )


@app.get("/runs", response_class=HTMLResponse)
def runs_page(request: Request):
    denial = require_admin(request)
    if denial:
        return denial
    with SessionLocal() as session:
        runs = session.scalars(select(RunLog).order_by(desc(RunLog.started_at)).limit(100)).all()
    return templates.TemplateResponse(
        request,
        "runs.html",
        {"runs": runs}
    )

@app.get("/resumes", response_class=HTMLResponse)
def resumes_page(request: Request, user_id: str | None = None):
    denial = require_admin(request)
    if denial:
        return denial
    with SessionLocal() as session:
        users = session.scalars(select(User).order_by(User.display_name)).all()
        selected_user_id = user_id or current_user_id(request)
        if selected_user_id and not session.get(User, selected_user_id):
            selected_user_id = current_user_id(request)
        assets = session.scalars(
            select(ResumeAsset)
            .where(ResumeAsset.user_id == selected_user_id)
            .order_by(desc(ResumeAsset.uploaded_at))
        ).all()
    return templates.TemplateResponse(
        request,
        "resumes.html",
        {"assets": assets, "users": users, "selected_user_id": selected_user_id}
    )

@app.post("/resumes/upload")
async def upload_resume(
    request: Request,
    resume_type: str = Form(...),
    user_id: str = Form(""),
    resume: UploadFile = File(...),
):
    denial = require_admin(request)
    if denial:
        return denial
    if resume_type not in {"focused", "all-work-experience"}:
        return JSONResponse({"error": "invalid resume type"}, status_code=400)

    filename = resume.filename or "resume.docx"
    if not filename.lower().endswith((".docx", ".pdf")):
        return JSONResponse({"error": "upload a DOCX or PDF resume"}, status_code=400)

    content = await resume.read()
    if len(content) > 10 * 1024 * 1024:
        return JSONResponse({"error": "resume exceeds 10 MB"}, status_code=400)

    with SessionLocal() as session:
        target_user_id = user_id or current_user_id(request)
        if not target_user_id or not session.get(User, target_user_id):
            return JSONResponse({"error": "invalid user"}, status_code=400)
        uri = save_resume(filename, content, resume_type, target_user_id)
        previous = session.scalars(
            select(ResumeAsset).where(
                ResumeAsset.user_id == target_user_id,
                ResumeAsset.resume_type == resume_type,
                ResumeAsset.is_current.is_(True),
            )
        ).all()
        for p in previous:
            p.is_current = False
        session.add(ResumeAsset(
            user_id=target_user_id,
            resume_type=resume_type,
            filename=filename,
            storage_uri=uri,
            uploaded_at=datetime.now(timezone.utc),
            is_current=True,
        ))
        session.commit()
    return RedirectResponse(f"/resumes?user_id={target_user_id}", status_code=303)
