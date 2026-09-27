\
from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, Request, Form, UploadFile, File, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, Response
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from sqlalchemy import select, desc, func, and_, case

from job_agent.db import init_db, SessionLocal
from job_agent.models import (
    Job, Evaluation, SearchTerm, RunLog, ResumeAsset, ApplicationPackage,
    User, UserJobState, CandidateProfile, UserPreference, Notification, AuditEvent,
    UserSearchTerm, UserJobMatch, AuthToken, UserOnboarding,
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
    empty_candidate_profile,
    ensure_user_profile_records,
    profile_identity_matches,
    seed_admin_profile,
    search_term_alignment,
    structured_candidate_profile,
    validate_candidate_profile,
)
from job_agent.profile_extractor import propose_profile_from_resume
from job_agent.analytics import build_admin_analytics, resolve_date_range
from job_agent.preflight import production_readiness
from job_agent.backfill import backfill_progress, request_backfill
from job_agent.user_search import (
    ensure_user_search_terms,
    normalize_search_term,
    seed_legacy_job_matches,
)
from job_agent.application_assistant import (
    ensure_assistant_profile,
    save_assistant_profile,
    user_for_extension_token,
)




from .cloud_trigger import trigger_worker
from .resume_storage import extract_resume_text, read_resume, save_resume
from .auth import (
    bootstrap_admin,
    consume_token,
    database_auth_enabled,
    find_user_by_email,
    find_valid_token,
    hash_password,
    issue_token,
    new_numeric_code,
    normalize_login_email,
    record_audit,
    token_digest,
    update_user_identity,
    utc_aware,
    verify_password,
    set_temporary_password,
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


def administrator_job_rows(session, sort_by: str = "newest_posted"):
    """Return jobs with current, cross-user fit and application metrics."""
    assignments = (
        select(
            UserJobMatch.user_id.label("user_id"),
            UserJobMatch.job_id.label("job_id"),
        )
        .join(User, User.id == UserJobMatch.user_id)
        .where(User.status == "active")
        .distinct()
        .subquery()
    )
    delivered = (
        select(
            Notification.user_id.label("user_id"),
            Notification.job_id.label("job_id"),
        )
        .where(Notification.status == "sent")
        .distinct()
        .subquery()
    )

    assigned_users = func.count(func.distinct(assignments.c.user_id))
    evaluated_users = func.count(func.distinct(case(
        (Evaluation.id.is_not(None), assignments.c.user_id),
        else_=None,
    )))
    best_fit = func.max(Evaluation.fit_score)
    average_fit = func.avg(Evaluation.fit_score)
    strong_fits = func.count(func.distinct(case(
        (Evaluation.fit_score >= 75, assignments.c.user_id),
        else_=None,
    )))
    apply_recommendations = func.count(func.distinct(case(
        (func.lower(Evaluation.recommendation) == "apply", assignments.c.user_id),
        else_=None,
    )))
    applied_users = func.count(func.distinct(case(
        (
            (UserJobState.applied_at.is_not(None))
            | (UserJobState.status.in_({"applied", "interview", "hired"})),
            assignments.c.user_id,
        ),
        else_=None,
    )))
    notified_users = func.count(func.distinct(delivered.c.user_id))

    stmt = (
        select(
            Job,
            assigned_users.label("assigned_users"),
            evaluated_users.label("evaluated_users"),
            best_fit.label("best_fit"),
            average_fit.label("average_fit"),
            strong_fits.label("strong_fits"),
            apply_recommendations.label("apply_recommendations"),
            notified_users.label("notified_users"),
            applied_users.label("applied_users"),
        )
        .join(assignments, assignments.c.job_id == Job.id)
        .join(
            CandidateProfile,
            CandidateProfile.user_id == assignments.c.user_id,
            isouter=True,
        )
        .join(
            Evaluation,
            and_(
                Evaluation.job_id == Job.id,
                Evaluation.user_id == assignments.c.user_id,
                Evaluation.resume_version == CandidateProfile.resume_version,
            ),
            isouter=True,
        )
        .join(
            UserJobState,
            and_(
                UserJobState.job_id == Job.id,
                UserJobState.user_id == assignments.c.user_id,
            ),
            isouter=True,
        )
        .join(
            delivered,
            and_(
                delivered.c.job_id == Job.id,
                delivered.c.user_id == assignments.c.user_id,
            ),
            isouter=True,
        )
        # PostgreSQL can project a table's columns when grouped by its primary
        # key. Grouping every column would include Job.requirements (JSON),
        # which has no PostgreSQL equality operator.
        .group_by(Job.id)
    )

    if sort_by == "highest_fit":
        stmt = stmt.order_by(best_fit.desc().nullslast(), Job.posted_at.desc().nullslast())
    elif sort_by == "lowest_fit":
        stmt = stmt.order_by(best_fit.asc().nullslast(), Job.posted_at.desc().nullslast())
    else:
        stmt = stmt.order_by(*job_sort_order(sort_by))
    return session.execute(stmt.limit(250)).all()


def administrator_notification_candidates(session, job_id: str) -> list[dict]:
    """Return active, assigned users with a score for administrator review."""
    assignments = (
        select(UserJobMatch.user_id)
        .where(UserJobMatch.job_id == job_id)
        .distinct()
        .subquery()
    )
    delivered = (
        select(Notification.user_id)
        .where(
            Notification.job_id == job_id,
            Notification.status == "sent",
        )
        .distinct()
        .subquery()
    )
    rows = session.execute(
        select(
            User,
            UserPreference,
            Evaluation,
            delivered.c.user_id.label("notified_user_id"),
        )
        .join(assignments, assignments.c.user_id == User.id)
        .join(CandidateProfile, CandidateProfile.user_id == User.id)
        .join(
            Evaluation,
            and_(
                Evaluation.user_id == User.id,
                Evaluation.job_id == job_id,
                Evaluation.resume_version == CandidateProfile.resume_version,
            ),
        )
        .join(UserPreference, UserPreference.user_id == User.id, isouter=True)
        .join(delivered, delivered.c.user_id == User.id, isouter=True)
        .where(User.status == "active")
        .order_by(Evaluation.fit_score.desc(), User.display_name)
    ).all()
    return [
        {
            "user": user,
            "preference": preference,
            "evaluation": evaluation,
            "recipient": (
                preference.notification_email
                if preference and preference.notification_email
                else user.email
            ),
            "previously_notified": notified_user_id is not None,
            "recommended": evaluation.recommendation.casefold() == "apply",
        }
        for user, preference, evaluation, notified_user_id in rows
    ]


def send_administrator_job_notifications(
    session,
    job: Job,
    candidates: list[dict],
    selected_user_ids: set[str],
    allow_resend: bool = False,
    sender=email_notify,
) -> dict[str, int]:
    """Send reviewed job alerts and persist every delivery attempt."""
    counts = {"sent": 0, "failed": 0, "skipped": 0}
    job_payload = {
        "title": job.title,
        "company": job.company,
        "location": job.location,
        "freshness_status": job.freshness_status,
        "apply_url": job.apply_url,
    }
    now = datetime.now(timezone.utc)
    for candidate in candidates:
        user = candidate["user"]
        if user.id not in selected_user_ids:
            continue
        if candidate["previously_notified"] and not allow_resend:
            counts["skipped"] += 1
            continue
        evaluation = candidate["evaluation"]
        evaluation_payload = {
            "fit_score": evaluation.fit_score,
            "classification": evaluation.classification,
            "recommendation": evaluation.recommendation,
            "selected_resume": evaluation.selected_resume,
            "reasoning": evaluation.reasoning,
            "missing_requirements": evaluation.missing_requirements or [],
        }
        sent, detail = sender(
            job_payload,
            evaluation_payload,
            "administrator selected job alert",
            recipient=candidate["recipient"],
        )
        session.add(Notification(
            user_id=user.id,
            job_id=job.id,
            evaluation_id=evaluation.id,
            channel="email" if sent else "console",
            sent_at=now,
            status="sent" if sent else "not_sent",
            detail=f"Administrator initiated: {detail}",
        ))
        counts["sent" if sent else "failed"] += 1
    session.commit()
    return counts

app = FastAPI(title="Calaveras Job Agent")


class BrowserSecurityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            source = request.headers.get("origin") or request.headers.get("referer")
            if source:
                source_host = urlsplit(source).netloc.lower()
                request_host = (
                    request.headers.get("x-forwarded-host")
                    or request.headers.get("host", "")
                ).split(",", 1)[0].strip().lower()
                if source_host != request_host:
                    return HTMLResponse("Cross-site request rejected", status_code=403)
            elif env("APP_ENV", "development") == "production":
                return HTMLResponse("Request origin required", status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
            "script-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
        )
        return response


app.add_middleware(BrowserSecurityMiddleware)
app.add_middleware(
    SessionMiddleware,
    secret_key=env("SESSION_SECRET", "dev-only-change-me"),
    https_only=(env("APP_ENV", "development") == "production"),
    same_site="lax",
    max_age=60 * 60 * 12,
)

def authed(request: Request) -> bool:
    return bool(request.session.get("user_id") or request.session.get("authenticated"))

def admin_user(request: Request) -> bool:
    return authed(request) and request.session.get("role", "administrator") == "administrator"

def current_user_id(request: Request) -> str | None:
    return request.session.get("user_id")


def administrator_notification_email(session, user_id: str | None) -> str:
    """Resolve the dashboard test-email recipient for the signed-in admin."""
    user = session.get(User, user_id) if user_id else None
    preference = session.get(UserPreference, user_id) if user_id else None
    if preference and preference.notification_email:
        return preference.notification_email
    if user:
        return user.email
    return env("ALERT_EMAIL_TO", "")


def owner_clause(column, request: Request):
    user_id = current_user_id(request)
    return column == user_id if user_id else column.is_(None)


def assigned_job_clause(request: Request):
    user_id = current_user_id(request)
    if not user_id:
        return None
    return Job.id.in_(
        select(UserJobMatch.job_id).where(UserJobMatch.user_id == user_id)
    )


def get_assigned_job(session, job_id: str, request: Request):
    assignment = assigned_job_clause(request)
    stmt = select(Job).where(Job.id == job_id)
    if assignment is not None:
        stmt = stmt.where(assignment)
    return session.scalar(stmt)

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


def require_admin_or_self(request: Request, user_id: str):
    denial = require_auth(request)
    if denial:
        return denial
    if not admin_user(request) and current_user_id(request) != user_id:
        return HTMLResponse("Access denied", status_code=403)
    return None


def bearer_token(request: Request) -> str | None:
    authorization = request.headers.get("authorization", "")
    scheme, _, value = authorization.partition(" ")
    if scheme.casefold() != "bearer" or not value.strip():
        return None
    return value.strip()


def send_invitation(session, user: User, request: Request) -> tuple[bool, str]:
    raw_token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(hours=48)
    issue_token(
        session,
        user,
        "onboarding_invite",
        raw_token,
        minutes=48 * 60,
    )
    onboarding = session.get(UserOnboarding, user.id)
    if not onboarding:
        onboarding = UserOnboarding(
            user_id=user.id,
            invited_at=now,
            invitation_expires_at=expires_at,
            updated_at=now,
        )
        session.add(onboarding)
    else:
        onboarding.invited_at = now
        onboarding.invitation_expires_at = expires_at
        onboarding.updated_at = now
    session.commit()
    base_url = (env("PUBLIC_BASE_URL") or str(request.base_url)).rstrip("/")
    invitation_url = f"{base_url}/onboarding/accept?token={raw_token}"
    sent, detail = email_text(
        user.email,
        "Complete your Calaveras Job Agent account",
        f"Hello {user.display_name},\n\n"
        "You have been invited to Calaveras Job Agent. Use this private link "
        "within 48 hours to create your password and verify your email:\n\n"
        f"{invitation_url}\n\n"
        "After verification, the onboarding guide will help you add your "
        "resume or LinkedIn profile, job-search terms, alerts, and application answers.\n\n"
        "If you were not expecting this invitation, ignore this email.",
    )
    return sent, detail

@app.on_event("startup")
def startup():
    if env("APP_ENV", "development") == "production" and database_auth_enabled():
        readiness_errors = production_readiness()
        if readiness_errors:
            raise RuntimeError(
                "Database authentication rollout blocked: "
                + " ".join(readiness_errors)
            )
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
        seed_legacy_job_matches(session)

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
                or user.status not in {"active", "onboarding"}
                or (user.locked_until and utc_aware(user.locked_until) > now)
                or not verify_password(password, user.password_hash)
            ):
                if user and user.status in {"active", "onboarding"}:
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
        admin_identity = None
        with SessionLocal() as session:
            admin = bootstrap_admin(session)
            assign_legacy_records_to_admin(session, admin)
            if admin:
                admin_identity = (admin.id, admin.email)
        request.session["authenticated"] = True
        request.session["role"] = "administrator"
        if admin_identity:
            request.session["user_id"] = admin_identity[0]
            request.session["email"] = admin_identity[1]
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
            if user and user.status in {"active", "onboarding"}:
                raw_token = secrets.token_urlsafe(32)
                issue_token(session, user, "password_reset", raw_token, minutes=30)
                public_base_url = (env("PUBLIC_BASE_URL") or str(request.base_url)).rstrip("/")
                reset_url = f"{public_base_url}/reset-password?token={raw_token}"
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


@app.get("/onboarding/accept", response_class=HTMLResponse)
def accept_invitation_page(request: Request, token: str = ""):
    with SessionLocal() as session:
        token_row = find_valid_token(session, "onboarding_invite", token)
        user = session.get(User, token_row.user_id) if token_row else None
    return templates.TemplateResponse(request, "accept_invitation.html", {
        "token": token,
        "user": user,
        "error": None if user else "This invitation is invalid or expired.",
    }, status_code=200 if user else 400)


@app.post("/onboarding/accept", response_class=HTMLResponse)
def accept_invitation(
    request: Request,
    token: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
):
    error = None
    if new_password != confirm_password:
        error = "Passwords do not match."
    with SessionLocal() as session:
        token_row = find_valid_token(session, "onboarding_invite", token)
        user = session.get(User, token_row.user_id) if token_row else None
        if not user:
            error = "This invitation is invalid or expired."
        password_hash = None
        if not error:
            try:
                password_hash = hash_password(new_password)
            except ValueError as exc:
                error = str(exc)
        if error:
            return templates.TemplateResponse(request, "accept_invitation.html", {
                "token": token,
                "user": user,
                "error": error,
            }, status_code=400)

        code = new_numeric_code()
        issue_token(session, user, "onboarding_otp", code, minutes=10)
        sent, _ = email_text(
            user.email,
            "Verify your Calaveras Job Agent email",
            f"Your six-digit verification code is: {code}\n\n"
            "This code expires in 10 minutes.",
        )
        if not sent:
            return templates.TemplateResponse(request, "accept_invitation.html", {
                "token": token,
                "user": user,
                "error": "The verification code could not be sent. Please try again.",
            }, status_code=503)

        user.password_hash = password_hash
        user.updated_at = datetime.now(timezone.utc)
        onboarding = session.get(UserOnboarding, user.id)
        if onboarding:
            onboarding.password_set_at = user.updated_at
            onboarding.updated_at = user.updated_at
        session.commit()
        consume_token(session, user, "onboarding_invite", token)
        record_audit(
            session,
            "onboarding_password_created",
            target_user_id=user.id,
            request=request,
        )
        request.session.clear()
        request.session["pending_onboarding_user_id"] = user.id
    return RedirectResponse("/onboarding/verify", status_code=303)


@app.get("/onboarding/verify", response_class=HTMLResponse)
def verify_onboarding_page(request: Request):
    if not request.session.get("pending_onboarding_user_id"):
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse(
        request,
        "verify_onboarding.html",
        {"error": None},
    )


@app.post("/onboarding/verify", response_class=HTMLResponse)
def verify_onboarding(request: Request, code: str = Form(...)):
    user_id = request.session.get("pending_onboarding_user_id")
    with SessionLocal() as session:
        user = session.get(User, user_id) if user_id else None
        if not user or not consume_token(session, user, "onboarding_otp", code):
            return templates.TemplateResponse(
                request,
                "verify_onboarding.html",
                {"error": "Invalid or expired code."},
                status_code=401,
            )
        now = datetime.now(timezone.utc)
        user.status = "onboarding"
        user.must_change_password = False
        user.last_login_at = now
        user.updated_at = now
        onboarding = session.get(UserOnboarding, user.id)
        if onboarding:
            onboarding.email_verified_at = now
            onboarding.updated_at = now
        session.commit()
        ensure_user_profile_records(session, user)
        ensure_user_search_terms(session, user)
        record_audit(
            session,
            "onboarding_email_verified",
            actor_user_id=user.id,
            target_user_id=user.id,
            request=request,
        )
        request.session.clear()
        request.session.update({
            "user_id": user.id,
            "role": user.role,
            "email": user.email,
            "must_change_password": False,
        })
    return RedirectResponse("/onboarding", status_code=303)


@app.post("/onboarding/resend-code")
def resend_onboarding_code(request: Request):
    user_id = request.session.get("pending_onboarding_user_id")
    with SessionLocal() as session:
        user = session.get(User, user_id) if user_id else None
        if not user or user.status != "invited":
            return RedirectResponse("/login", status_code=303)
        code = new_numeric_code()
        issue_token(session, user, "onboarding_otp", code, minutes=10)
        sent, _ = email_text(
            user.email,
            "Verify your Calaveras Job Agent email",
            f"Your six-digit verification code is: {code}\n\n"
            "This code expires in 10 minutes.",
        )
    message = "A+new+code+was+sent" if sent else "The+code+could+not+be+sent"
    return RedirectResponse(f"/onboarding/verify?message={message}", status_code=303)


@app.get("/onboarding", response_class=HTMLResponse)
def onboarding_page(request: Request):
    denial = require_auth(request)
    if denial:
        return denial
    with SessionLocal() as session:
        user = session.get(User, current_user_id(request))
        if not user:
            return HTMLResponse("User not found", status_code=404)
        onboarding = session.get(UserOnboarding, user.id)
        profile = session.get(CandidateProfile, user.id)
        source_count = session.scalar(
            select(func.count(ResumeAsset.id)).where(
                ResumeAsset.user_id == user.id,
                ResumeAsset.is_current.is_(True),
            )
        ) or 0
        term_count = session.scalar(
            select(func.count(UserSearchTerm.id)).where(
                UserSearchTerm.user_id == user.id,
                UserSearchTerm.enabled.is_(True),
            )
        ) or 0
        preference = session.get(UserPreference, user.id)
        steps = {
            "account": bool(onboarding and onboarding.email_verified_at),
            "source": source_count > 0,
            "profile": bool(profile and profile.is_active),
            "search": term_count > 0,
            "notifications": bool(preference and preference.notification_email),
        }
        existing_user = onboarding is None
        complete = existing_user or all(steps.values())
        if onboarding and complete and not onboarding.completed_at:
            onboarding.completed_at = datetime.now(timezone.utc)
            onboarding.updated_at = onboarding.completed_at
            user.status = "active"
            user.updated_at = onboarding.completed_at
            session.commit()
            record_audit(
                session,
                "onboarding_completed",
                actor_user_id=user.id,
                target_user_id=user.id,
                request=request,
            )
    return templates.TemplateResponse(request, "onboarding.html", {
        "user": user,
        "steps": steps,
        "complete": complete,
        "existing_user": existing_user,
    })

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
        assignment = assigned_job_clause(request)
        total_stmt = select(func.count(Job.id))
        if assignment is not None:
            total_stmt = total_stmt.where(assignment)
        total_jobs = session.scalar(total_stmt) or 0
        strong = session.scalar(
            select(func.count(Evaluation.id)).where(
                owner_clause(Evaluation.user_id, request),
                Evaluation.resume_version == resume_version,
                Evaluation.fit_score >= 75,
            )
        ) or 0
        recent_stmt = (
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
        if assignment is not None:
            recent_stmt = recent_stmt.where(assignment)
        recent = session.execute(recent_stmt.limit(8)).all()

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
        recipient = administrator_notification_email(
            session,
            current_user_id(request),
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
            "evaluation_batch_size": get_int(session, "evaluation_batch_size", 12),
            "backfill_batch_size": get_int(session, "backfill_batch_size", 6),
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
            "schedule_days": {
                 int(day)
                 for day in (
                     get_setting(session, "schedule_days", "0,1,2,3,4") or ""
                 ).split(",")
                 if day.strip().isdigit()
            },
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
    evaluation_batch_size: int = Form(12),
    backfill_batch_size: int = Form(6),
    schedule_interval_minutes: int = Form(...),
    schedule_start_time: str = Form(...),
    schedule_stop_time: str = Form(...),
    schedule_days: list[str] = Form([]),
    allow_unverified_current_jobs_in_digest: str | None = Form(None),
):
    denial = require_admin(request)
    if denial:
        return denial
    with SessionLocal() as session:
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
        batch_size = max(1, min(50, evaluation_batch_size))
        set_setting(session, "evaluation_batch_size", str(batch_size))
        set_setting(
            session,
            "backfill_batch_size",
            str(max(0, min(batch_size, backfill_batch_size))),
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
        if admin_user(request):
            rows = administrator_job_rows(session, sort)
            return templates.TemplateResponse(
                request,
                "jobs.html",
                {
                    "rows": rows,
                    "status_filter": None,
                    "sort_by": sort,
                    "administrator_view": True,
                },
            )

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
        assignment = assigned_job_clause(request)
        if assignment is not None:
            stmt = stmt.where(assignment)
        if status:
            if current_user_id(request):
                stmt = stmt.where(UserJobState.status == status)
            else:
                stmt = stmt.where(Job.status == status)
        rows = session.execute(stmt.limit(250)).all()
    return templates.TemplateResponse(
        request,
        "jobs.html",
        {
            "rows": rows,
            "status_filter": status,
            "sort_by": sort,
            "administrator_view": False,
        }
    )


@app.get("/admin/jobs/{job_id}/notify", response_class=HTMLResponse)
def administrator_job_notification_page(job_id: str, request: Request):
    denial = require_admin(request)
    if denial:
        return denial
    with SessionLocal() as session:
        job = session.get(Job, job_id)
        if not job:
            return HTMLResponse("Job not found", status_code=404)
        candidates = administrator_notification_candidates(session, job_id)
    return templates.TemplateResponse(
        request,
        "job_notify.html",
        {"job": job, "candidates": candidates},
    )


@app.post("/admin/jobs/{job_id}/notify")
def send_administrator_job_notification(
    job_id: str,
    request: Request,
    user_ids: list[str] = Form([]),
    allow_resend: str | None = Form(None),
):
    denial = require_admin(request)
    if denial:
        return denial
    if not user_ids:
        return RedirectResponse(
            f"/admin/jobs/{job_id}/notify?message=Select+at+least+one+user",
            status_code=303,
        )
    with SessionLocal() as session:
        job = session.get(Job, job_id)
        if not job:
            return HTMLResponse("Job not found", status_code=404)
        candidates = administrator_notification_candidates(session, job_id)
        counts = send_administrator_job_notifications(
            session,
            job,
            candidates,
            set(user_ids),
            allow_resend=allow_resend == "on",
        )
        record_audit(
            session,
            "administrator_job_notification",
            actor_user_id=current_user_id(request),
            request=request,
            detail={"job_id": job_id, **counts},
        )
    message = (
        f"Sent+{counts['sent']}"
        f";+failed+{counts['failed']}"
        f";+skipped+{counts['skipped']}"
    )
    return RedirectResponse(f"/jobs?message={message}", status_code=303)

@app.post("/jobs/{job_id}/status")
def set_job_status(job_id: str, request: Request, status: str = Form(...)):
    denial = require_auth(request)
    if denial:
        return denial
    allowed = {"new", "reviewed", "interested", "applied", "interview", "rejected", "hired", "ignore", "expired"}
    if status not in allowed:
        return JSONResponse({"error": "invalid status"}, status_code=400)
    with SessionLocal() as session:
        job = get_assigned_job(session, job_id, request)
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
        job = get_assigned_job(session, job_id, request)
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
        job = get_assigned_job(session, job_id, request)
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
        job = get_assigned_job(session, job_id, request)
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


@app.get("/application-assistant", response_class=HTMLResponse)
def application_assistant_page(request: Request):
    denial = require_auth(request)
    if denial:
        return denial
    with SessionLocal() as session:
        user = session.get(User, current_user_id(request))
        if not user:
            return HTMLResponse("User not found", status_code=404)
        assistant = ensure_assistant_profile(session, user)
        active_token = session.scalar(
            select(AuthToken)
            .where(
                AuthToken.user_id == user.id,
                AuthToken.purpose == "application_assistant",
                AuthToken.used_at.is_(None),
                AuthToken.expires_at > datetime.now(timezone.utc),
            )
            .order_by(desc(AuthToken.created_at))
            .limit(1)
        )
    return templates.TemplateResponse(request, "application_assistant.html", {
        "user": user,
        "assistant": assistant,
        "active_token": active_token,
        "new_token": None,
    })


@app.post("/application-assistant/profile", response_class=HTMLResponse)
def save_application_assistant_page(
    request: Request,
    phone: str = Form(""),
    address_line_1: str = Form(""),
    address_line_2: str = Form(""),
    city: str = Form(""),
    state: str = Form(""),
    postal_code: str = Form(""),
    country: str = Form("United States"),
    linkedin_url: str = Form(""),
    authorized_to_work: str = Form("review"),
    requires_sponsorship: str = Form("review"),
    willing_to_relocate: str = Form("review"),
    available_start_date: str = Form(""),
    desired_salary: str = Form(""),
    remote_preference: str = Form(""),
):
    denial = require_auth(request)
    if denial:
        return denial
    with SessionLocal() as session:
        user = session.get(User, current_user_id(request))
        if not user:
            return HTMLResponse("User not found", status_code=404)
        try:
            save_assistant_profile(
                session,
                user,
                {
                    "phone": phone,
                    "address_line_1": address_line_1,
                    "address_line_2": address_line_2,
                    "city": city,
                    "state": state,
                    "postal_code": postal_code,
                    "country": country,
                    "linkedin_url": linkedin_url,
                },
                {
                    "authorized_to_work": authorized_to_work,
                    "requires_sponsorship": requires_sponsorship,
                    "willing_to_relocate": willing_to_relocate,
                    "available_start_date": available_start_date,
                    "desired_salary": desired_salary,
                    "remote_preference": remote_preference,
                },
            )
        except ValueError as exc:
            return HTMLResponse(str(exc), status_code=400)
        record_audit(
            session,
            "application_assistant_profile_updated",
            actor_user_id=user.id,
            target_user_id=user.id,
            request=request,
        )
    return RedirectResponse(
        "/application-assistant?message=Application+answers+saved",
        status_code=303,
    )


@app.post("/application-assistant/token", response_class=HTMLResponse)
def create_application_assistant_token(request: Request):
    denial = require_auth(request)
    if denial:
        return denial
    raw_token = secrets.token_urlsafe(32)
    with SessionLocal() as session:
        user = session.get(User, current_user_id(request))
        if not user:
            return HTMLResponse("User not found", status_code=404)
        assistant = ensure_assistant_profile(session, user)
        active_token = issue_token(
            session,
            user,
            "application_assistant",
            raw_token,
            minutes=60 * 24 * 90,
        )
        record_audit(
            session,
            "application_assistant_token_created",
            actor_user_id=user.id,
            target_user_id=user.id,
            request=request,
        )
    return templates.TemplateResponse(request, "application_assistant.html", {
        "user": user,
        "assistant": assistant,
        "active_token": active_token,
        "new_token": raw_token,
    })


@app.post("/application-assistant/token/revoke")
def revoke_application_assistant_token(request: Request):
    denial = require_auth(request)
    if denial:
        return denial
    now = datetime.now(timezone.utc)
    with SessionLocal() as session:
        user_id = current_user_id(request)
        tokens = session.scalars(
            select(AuthToken).where(
                AuthToken.user_id == user_id,
                AuthToken.purpose == "application_assistant",
                AuthToken.used_at.is_(None),
            )
        ).all()
        for token in tokens:
            token.used_at = now
        session.commit()
        record_audit(
            session,
            "application_assistant_token_revoked",
            actor_user_id=user_id,
            target_user_id=user_id,
            request=request,
        )
    return RedirectResponse(
        "/application-assistant?message=Extension+access+revoked",
        status_code=303,
    )


@app.get("/api/application-assistant/profile")
def application_assistant_api_profile(request: Request):
    with SessionLocal() as session:
        user = user_for_extension_token(session, bearer_token(request))
        if not user:
            return JSONResponse(
                {"error": "invalid or expired access token"},
                status_code=401,
                headers={"Cache-Control": "no-store"},
            )
        assistant = ensure_assistant_profile(session, user)
        resumes = session.scalars(
            select(ResumeAsset)
            .where(
                ResumeAsset.user_id == user.id,
                ResumeAsset.resume_type.in_(("focused", "all-work-experience")),
                ResumeAsset.is_current.is_(True),
            )
            .order_by(ResumeAsset.resume_type)
        ).all()
        payload = {
            "identity": {
                "full_name": user.display_name,
                "email": user.email,
                **assistant.contact_data,
            },
            "standard_answers": assistant.standard_answers,
            "resumes": [
                {
                    "id": asset.id,
                    "type": asset.resume_type,
                    "filename": asset.filename,
                    "download_path": f"/api/application-assistant/resumes/{asset.id}",
                }
                for asset in resumes
            ],
        }
    return JSONResponse(payload, headers={"Cache-Control": "no-store"})


@app.get("/api/application-assistant/resumes/{asset_id}")
def application_assistant_api_resume(asset_id: str, request: Request):
    with SessionLocal() as session:
        user = user_for_extension_token(session, bearer_token(request))
        if not user:
            return JSONResponse(
                {"error": "invalid or expired access token"},
                status_code=401,
                headers={"Cache-Control": "no-store"},
            )
        asset = session.get(ResumeAsset, asset_id)
        if (
            not asset
            or asset.user_id != user.id
            or asset.resume_type not in {"focused", "all-work-experience"}
            or not asset.is_current
        ):
            return JSONResponse({"error": "resume not found"}, status_code=404)
        try:
            content = read_resume(asset.storage_uri)
        except Exception:
            return JSONResponse({"error": "resume unavailable"}, status_code=404)
        filename = Path(asset.filename).name.replace('"', "")
        media_type = (
            "application/pdf"
            if filename.casefold().endswith(".pdf")
            else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
    return Response(
        content,
        media_type=media_type,
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


@app.get("/admin/users", response_class=HTMLResponse)
def users_page(request: Request):
    denial = require_admin(request)
    if denial:
        return denial
    with SessionLocal() as session:
        users = session.scalars(select(User).order_by(User.created_at.desc())).all()
        onboarding = {
            row.user_id: row
            for row in session.scalars(select(UserOnboarding)).all()
        }
    return templates.TemplateResponse(request, "users.html", {
        "users": users,
        "onboarding": onboarding,
    })


def analytics_context(period: str, start: str | None, end: str | None):
    start_utc, end_utc, range_label = resolve_date_range(period, start, end)
    with SessionLocal() as session:
        analytics = build_admin_analytics(session, start_utc, end_utc)
    return {
        "analytics": analytics,
        "period": period,
        "start": start or "",
        "end": end or "",
        "range_label": range_label,
    }


@app.get("/admin/analytics", response_class=HTMLResponse)
def analytics_page(
    request: Request,
    period: str = "30d",
    start: str | None = None,
    end: str | None = None,
):
    denial = require_admin(request)
    if denial:
        return denial
    return templates.TemplateResponse(
        request,
        "analytics.html",
        analytics_context(period, start, end),
    )


@app.get("/admin/notifications", response_class=HTMLResponse)
def notifications_page(
    request: Request,
    period: str = "30d",
    start: str | None = None,
    end: str | None = None,
):
    denial = require_admin(request)
    if denial:
        return denial
    return templates.TemplateResponse(
        request,
        "notifications.html",
        analytics_context(period, start, end),
    )


@app.get("/admin/users/{user_id}/activity", response_class=HTMLResponse)
def user_activity_page(
    user_id: str,
    request: Request,
    period: str = "30d",
    start: str | None = None,
    end: str | None = None,
):
    denial = require_admin(request)
    if denial:
        return denial
    context = analytics_context(period, start, end)
    with SessionLocal() as session:
        user = session.get(User, user_id)
        if not user:
            return HTMLResponse("User not found", status_code=404)
    analytics = context["analytics"]
    context.update({
        "user": user,
        "user_notifications": [row for row in analytics["notifications"] if row["notification"].user_id == user_id],
        "user_applications": [row for row in analytics["applications"] if row["state"].user_id == user_id],
    })
    return templates.TemplateResponse(request, "user_activity.html", context)


@app.get("/admin/audit", response_class=HTMLResponse)
def audit_page(request: Request, event_type: str | None = None):
    denial = require_admin(request)
    if denial:
        return denial
    with SessionLocal() as session:
        users = {user.id: user for user in session.scalars(select(User)).all()}
        stmt = select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(500)
        if event_type:
            stmt = stmt.where(AuditEvent.event_type == event_type)
        events = session.scalars(stmt).all()
        event_types = session.scalars(
            select(AuditEvent.event_type).distinct().order_by(AuditEvent.event_type)
        ).all()
    return templates.TemplateResponse(request, "audit.html", {
        "events": events,
        "users": users,
        "event_types": event_types,
        "event_type": event_type or "",
    })


@app.post("/admin/users")
def create_user(
    request: Request,
    email: str = Form(...),
    display_name: str = Form(...),
):
    denial = require_admin(request)
    if denial:
        return denial
    normalized_email = normalize_login_email(email)
    if not normalized_email:
        return RedirectResponse("/admin/users?message=Enter+a+valid+email", status_code=303)
    with SessionLocal() as session:
        if find_user_by_email(session, normalized_email):
            return RedirectResponse("/admin/users?message=That+email+already+exists", status_code=303)
        now = datetime.now(timezone.utc)
        user = User(
            email=normalized_email,
            display_name=display_name.strip() or normalized_email,
            password_hash=hash_password(secrets.token_urlsafe(32)),
            role="user",
            status="invited",
            must_change_password=True,
            created_at=now,
            updated_at=now,
        )
        session.add(user)
        session.commit()
        sent, detail = send_invitation(session, user, request)
        record_audit(
            session,
            "user_invited" if sent else "user_invitation_failed",
            actor_user_id=request.session.get("user_id"),
            target_user_id=user.id,
            request=request,
            detail={"delivery": detail},
        )
    message = "Invitation+sent" if sent else "User+created;+invitation+email+failed"
    return RedirectResponse(f"/admin/users?message={message}", status_code=303)


@app.post("/admin/users/{user_id}/status")
def change_user_status(user_id: str, request: Request, status: str = Form(...)):
    denial = require_admin(request)
    if denial:
        return denial
    if status not in {"invited", "onboarding", "active", "suspended", "archived"}:
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


@app.get("/admin/users/{user_id}/account", response_class=HTMLResponse)
def user_account_page(user_id: str, request: Request):
    denial = require_admin(request)
    if denial:
        return denial
    with SessionLocal() as session:
        user = session.get(User, user_id)
        if not user:
            return HTMLResponse("User not found", status_code=404)
        profile = session.get(CandidateProfile, user_id)
        progress = (
            backfill_progress(session, user_id, profile.resume_version)
            if profile else {"completed": 0, "pending": 0, "request": None}
        )
        term_count = session.scalar(select(func.count(UserSearchTerm.id)).where(
            UserSearchTerm.user_id == user_id,
            UserSearchTerm.enabled.is_(True),
        )) or 0
        onboarding = session.get(UserOnboarding, user_id)
    return templates.TemplateResponse(request, "user_account.html", {
        "user": user,
        "profile": profile,
        "term_count": term_count,
        "backfill": progress,
        "onboarding": onboarding,
    })


@app.post("/admin/users/{user_id}/account/identity")
def edit_user_identity(
    user_id: str,
    request: Request,
    display_name: str = Form(...),
    email: str = Form(...),
):
    denial = require_admin(request)
    if denial:
        return denial
    with SessionLocal() as session:
        user = session.get(User, user_id)
        if not user:
            return HTMLResponse("User not found", status_code=404)
        old_email = user.email
        try:
            update_user_identity(session, user, email, display_name)
        except ValueError as exc:
            return RedirectResponse(
                f"/admin/users/{user_id}/account?message={str(exc).replace(' ', '+')}",
                status_code=303,
            )
        record_audit(
            session, "user_identity_updated",
            actor_user_id=current_user_id(request), target_user_id=user_id,
            request=request,
            detail={"old_email": old_email, "new_email": user.email},
        )
        if user_id == current_user_id(request):
            request.session["email"] = user.email
    return RedirectResponse(
        f"/admin/users/{user_id}/account?message=Account+updated",
        status_code=303,
    )


@app.post("/admin/users/{user_id}/account/temporary-password")
def issue_temporary_password(
    user_id: str,
    request: Request,
    temporary_password: str = Form(...),
    confirm_password: str = Form(...),
):
    denial = require_admin(request)
    if denial:
        return denial
    if user_id == current_user_id(request):
        return RedirectResponse(
            f"/admin/users/{user_id}/account?message=Use+Forgot+password+for+your+own+account",
            status_code=303,
        )
    if temporary_password != confirm_password:
        return RedirectResponse(
            f"/admin/users/{user_id}/account?message=Passwords+do+not+match",
            status_code=303,
        )
    with SessionLocal() as session:
        user = session.get(User, user_id)
        if not user:
            return HTMLResponse("User not found", status_code=404)
        try:
            set_temporary_password(session, user, temporary_password)
        except ValueError as exc:
            return RedirectResponse(
                f"/admin/users/{user_id}/account?message={str(exc).replace(' ', '+')}",
                status_code=303,
            )
        record_audit(
            session, "temporary_password_issued",
            actor_user_id=current_user_id(request), target_user_id=user_id,
            request=request,
        )
    return RedirectResponse(
        f"/admin/users/{user_id}/account?message=Temporary+password+updated",
        status_code=303,
    )


@app.post("/admin/users/{user_id}/account/send-onboarding")
def send_user_onboarding(user_id: str, request: Request):
    denial = require_admin(request)
    if denial:
        return denial
    with SessionLocal() as session:
        user = session.get(User, user_id)
        if not user:
            return HTMLResponse("User not found", status_code=404)
        if user.status == "invited":
            sent, _ = send_invitation(session, user, request)
            event_type = (
                "user_invitation_resent" if sent
                else "user_invitation_failed"
            )
            record_audit(
                session,
                event_type,
                actor_user_id=current_user_id(request),
                target_user_id=user_id,
                request=request,
            )
            message = (
                "Invitation+email+sent"
                if sent else "Invitation+email+could+not+be+sent"
            )
            return RedirectResponse(
                f"/admin/users/{user_id}/account?message={message}",
                status_code=303,
            )
        if user.status not in {"active", "onboarding"}:
            return RedirectResponse(
                f"/admin/users/{user_id}/account?message=Activate+the+account+before+sending+onboarding",
                status_code=303,
            )
        login_url = (env("PUBLIC_BASE_URL") or str(request.base_url)).rstrip("/") + "/login"
        sent, _ = email_text(
            user.email,
            "Your Calaveras Job Agent account",
            f"Hello {user.display_name},\n\n"
            "Your administrator has created your Calaveras Job Agent account. "
            "Use the temporary password provided separately. After signing in, "
            "a six-digit verification code will be emailed to you and you will "
            "be required to choose a new password.\n\n"
            f"Sign in: {login_url}\n\n"
            "If you were not expecting this account, contact your administrator.",
        )
        record_audit(
            session,
            "onboarding_email_sent" if sent else "onboarding_email_failed",
            actor_user_id=current_user_id(request), target_user_id=user_id,
            request=request,
        )
    message = "Onboarding+email+sent" if sent else "Onboarding+email+could+not+be+sent"
    return RedirectResponse(
        f"/admin/users/{user_id}/account?message={message}", status_code=303
    )


@app.get("/profile")
def own_profile_page(request: Request):
    denial = require_auth(request)
    if denial:
        return denial
    user_id = current_user_id(request)
    if not user_id:
        return HTMLResponse("Account ownership is required", status_code=409)
    return RedirectResponse(f"/admin/users/{user_id}/profile", status_code=303)


@app.get("/admin/users/{user_id}/profile", response_class=HTMLResponse)
def user_profile_page(user_id: str, request: Request):
    denial = require_admin_or_self(request, user_id)
    if denial:
        return denial
    with SessionLocal() as session:
        user = session.get(User, user_id)
        if not user:
            return HTMLResponse("User not found", status_code=404)
        profile, preference = ensure_user_profile_records(session, user)
        user_terms = ensure_user_search_terms(session, user)
        progress = backfill_progress(session, user.id, profile.resume_version)
    return templates.TemplateResponse(request, "user_profile.html", {
        "user": user,
        "profile": profile,
        "preference": preference,
        "profile_data": profile.profile_data,
        "saved_profile_data": None,
        "suggestion_asset": None,
        "review_mode": False,
        "backfill": progress,
        "user_terms": user_terms,
        "alignment": search_term_alignment(profile.profile_data, user_terms),
        "error": None,
    })


@app.post("/admin/users/{user_id}/profile", response_class=HTMLResponse)
def save_user_profile(
    user_id: str,
    request: Request,
    candidate_name: str = Form(...),
    location: str = Form(...),
    career_targets: str = Form(""),
    accounting_office: str = Form(""),
    data_technical: str = Form(""),
    operations: str = Form(""),
    transferable: str = Form(""),
    experience_role: list[str] = Form([]),
    experience_company: list[str] = Form([]),
    experience_location: list[str] = Form([]),
    experience_dates: list[str] = Form([]),
    experience_highlights: list[str] = Form([]),
    education_name: list[str] = Form([]),
    education_provider: list[str] = Form([]),
    education_status: list[str] = Form([]),
    focused_rules: str = Form(""),
    all_work_rules: str = Form(""),
    truth_constraints: str = Form(""),
    notification_email: str = Form(...),
    digest_time: str = Form("17:05"),
    is_active: str | None = Form(None),
    immediate_alerts: str | None = Form(None),
    daily_digest: str | None = Form(None),
    profile_review: str | None = Form(None),
    queue_backfill_after_save: str | None = Form(None),
):
    denial = require_admin_or_self(request, user_id)
    if denial:
        return denial
    profile_data = structured_candidate_profile(
        name=candidate_name,
        location=location,
        career_targets=career_targets,
        accounting_office=accounting_office,
        data_technical=data_technical,
        operations=operations,
        transferable=transferable,
        experience_roles=experience_role,
        experience_companies=experience_company,
        experience_locations=experience_location,
        experience_dates=experience_dates,
        experience_highlights=experience_highlights,
        education_names=education_name,
        education_providers=education_provider,
        education_statuses=education_status,
        focused_rules=focused_rules,
        all_work_rules=all_work_rules,
        truth_constraints=truth_constraints,
    )
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
        user_terms = ensure_user_search_terms(session, user)
        if errors:
            progress = backfill_progress(session, user.id, profile.resume_version)
            return templates.TemplateResponse(request, "user_profile.html", {
                "user": user,
                "profile": profile,
                "preference": preference,
                "profile_data": profile_data,
                "saved_profile_data": None,
                "suggestion_asset": None,
                "review_mode": profile_review == "on",
                "backfill": progress,
                "user_terms": user_terms,
                "alignment": search_term_alignment(profile_data, user_terms),
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
        queued = False
        if queue_backfill_after_save == "on" and profile.is_active:
            backfill = request_backfill(session, user.id)
            queued = True
            record_audit(
                session,
                "evaluation_backfill_requested",
                actor_user_id=current_user_id(request),
                target_user_id=user.id,
                request=request,
                detail={
                    "resume_version": profile.resume_version,
                    "pending": max(
                        0,
                        backfill.total_jobs - backfill.completed_jobs,
                    ),
                    "notifications": False,
                    "requested_with_profile_save": True,
                },
            )
    message = (
        "Profile+saved+and+score+backfill+queued"
        if queued
        else "Profile+saved"
    )
    return RedirectResponse(
        f"/admin/users/{user_id}/profile?message={message}",
        status_code=303,
    )


@app.post("/admin/users/{user_id}/search-terms")
def add_user_search_term(user_id: str, request: Request, term: str = Form(...)):
    denial = require_admin_or_self(request, user_id)
    if denial:
        return denial
    normalized = normalize_search_term(term)
    with SessionLocal() as session:
        user = session.get(User, user_id)
        if not user:
            return HTMLResponse("User not found", status_code=404)
        exists = session.scalar(select(UserSearchTerm).where(
            UserSearchTerm.user_id == user_id,
            func.lower(UserSearchTerm.term) == normalized.lower(),
        )) if normalized else None
        if normalized and not exists:
            new_term = UserSearchTerm(
                user_id=user_id, term=normalized, enabled=True,
                created_at=datetime.now(timezone.utc),
            )
            session.add(new_term)
            session.commit()
            record_audit(
                session, "user_search_term_added",
                actor_user_id=current_user_id(request), target_user_id=user_id,
                request=request, detail={"term": normalized},
            )
    return RedirectResponse(f"/admin/users/{user_id}/profile", status_code=303)


@app.post("/admin/users/{user_id}/search-terms/{term_id}/toggle")
def toggle_user_search_term(user_id: str, term_id: str, request: Request):
    denial = require_admin_or_self(request, user_id)
    if denial:
        return denial
    with SessionLocal() as session:
        term = session.scalar(select(UserSearchTerm).where(
            UserSearchTerm.id == term_id,
            UserSearchTerm.user_id == user_id,
        ))
        if term:
            term.enabled = not term.enabled
            session.commit()
            record_audit(
                session, "user_search_term_toggled",
                actor_user_id=current_user_id(request), target_user_id=user_id,
                request=request,
                detail={"term": term.term, "enabled": term.enabled},
            )
    return RedirectResponse(f"/admin/users/{user_id}/profile", status_code=303)


@app.post("/admin/users/{user_id}/search-terms/{term_id}/delete")
def delete_user_search_term(user_id: str, term_id: str, request: Request):
    denial = require_admin_or_self(request, user_id)
    if denial:
        return denial
    with SessionLocal() as session:
        term = session.scalar(select(UserSearchTerm).where(
            UserSearchTerm.id == term_id,
            UserSearchTerm.user_id == user_id,
        ))
        if term:
            deleted_term = term.term
            session.delete(term)
            session.commit()
            record_audit(
                session, "user_search_term_deleted",
                actor_user_id=current_user_id(request), target_user_id=user_id,
                request=request, detail={"term": deleted_term},
            )
    return RedirectResponse(f"/admin/users/{user_id}/profile", status_code=303)


@app.post("/admin/users/{user_id}/backfill")
def queue_user_backfill(user_id: str, request: Request):
    denial = require_admin_or_self(request, user_id)
    if denial:
        return denial
    with SessionLocal() as session:
        user = session.get(User, user_id)
        profile = session.get(CandidateProfile, user_id)
        if not user or not profile:
            return HTMLResponse("User not found", status_code=404)
        if not profile.is_active:
            return RedirectResponse(
                f"/admin/users/{user_id}/profile?message=Activate+the+profile+before+requesting+a+backfill",
                status_code=303,
            )
        backfill = request_backfill(session, user_id)
        record_audit(
            session,
            "evaluation_backfill_requested",
            actor_user_id=current_user_id(request),
            target_user_id=user_id,
            request=request,
            detail={
                "resume_version": profile.resume_version,
                "pending": max(0, backfill.total_jobs - backfill.completed_jobs),
                "notifications": False,
            },
        )
    return RedirectResponse(
        f"/admin/users/{user_id}/profile?message=Score+backfill+queued",
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
    denial = require_auth(request)
    if denial:
        return denial
    with SessionLocal() as session:
        if admin_user(request):
            users = session.scalars(select(User).order_by(User.display_name)).all()
            selected_user_id = user_id or current_user_id(request)
        else:
            selected_user_id = current_user_id(request)
            own_user = session.get(User, selected_user_id)
            users = [own_user] if own_user else []
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


@app.post("/resumes/{asset_id}/profile-suggestion", response_class=HTMLResponse)
def resume_profile_suggestion(asset_id: str, request: Request):
    denial = require_auth(request)
    if denial:
        return denial
    with SessionLocal() as session:
        asset = session.get(ResumeAsset, asset_id)
        if not asset or not asset.user_id:
            return HTMLResponse("Resume not found", status_code=404)
        if not admin_user(request) and asset.user_id != current_user_id(request):
            return HTMLResponse("Access denied", status_code=403)
        user = session.get(User, asset.user_id)
        if not user:
            return HTMLResponse("User not found", status_code=404)
        profile, preference = ensure_user_profile_records(session, user)
        user_terms = ensure_user_search_terms(session, user)
        progress = backfill_progress(session, user.id, profile.resume_version)
        enabled_terms = [term.term for term in user_terms if term.enabled]
        error = None
        identity_warning = None
        source_label = (
            "LinkedIn profile"
            if asset.resume_type == "linkedin-profile"
            else "resume"
        )
        proposal = profile.profile_data
        try:
            resume_text = asset.extracted_text
            if not resume_text:
                resume_content = read_resume(asset.storage_uri)
                resume_text = extract_resume_text(asset.filename, resume_content)
                asset.extracted_text = resume_text
                session.commit()
            merge_profile = profile.profile_data
            if not profile_identity_matches(
                profile.profile_data.get("name"),
                user.display_name,
            ):
                merge_profile = empty_candidate_profile(user)
                identity_warning = (
                    "The saved profile belonged to a different candidate and "
                    "was not used as the basis for this suggestion."
                )
            proposal = propose_profile_from_resume(
                resume_text,
                merge_profile,
                enabled_terms,
                candidate_name=user.display_name,
                source_label=source_label,
            )
        except Exception as exc:
            error = f"{source_label} review could not be prepared: {exc}"
        if not error:
            record_audit(
                session,
                "resume_profile_suggestion_generated",
                actor_user_id=current_user_id(request),
                target_user_id=user.id,
                request=request,
                detail={
                    "resume_asset_id": asset.id,
                    "filename": asset.filename,
                    "source_type": asset.resume_type,
                },
            )
    return templates.TemplateResponse(
        request,
        "user_profile.html",
        {
            "user": user,
            "profile": profile,
            "preference": preference,
            "profile_data": proposal,
            "saved_profile_data": profile.profile_data if not error else None,
            "suggestion_asset": asset if not error else None,
            "suggestion_source_label": source_label,
            "identity_warning": identity_warning,
            "review_mode": not error,
            "backfill": progress,
            "user_terms": user_terms,
            "alignment": search_term_alignment(proposal, user_terms),
            "error": error,
        },
        status_code=502 if error else 200,
    )

@app.post("/resumes/upload")
async def upload_resume(
    request: Request,
    resume_type: str = Form(...),
    user_id: str = Form(""),
    resume: UploadFile = File(...),
):
    denial = require_auth(request)
    if denial:
        return denial
    allowed_types = {"focused", "all-work-experience", "linkedin-profile"}
    if resume_type not in allowed_types:
        return JSONResponse({"error": "invalid document type"}, status_code=400)

    filename = resume.filename or "resume.docx"
    if resume_type == "linkedin-profile" and not filename.lower().endswith(".pdf"):
        return JSONResponse(
            {"error": "upload a LinkedIn profile PDF"}, status_code=400
        )
    if not filename.lower().endswith((".docx", ".pdf")):
        return JSONResponse({"error": "upload a DOCX or PDF resume"}, status_code=400)

    content = await resume.read()
    if len(content) > 10 * 1024 * 1024:
        return JSONResponse({"error": "resume exceeds 10 MB"}, status_code=400)
    try:
        extracted_text = extract_resume_text(filename, content)
    except Exception:
        extracted_text = None

    with SessionLocal() as session:
        target_user_id = user_id or current_user_id(request)
        if not admin_user(request):
            target_user_id = current_user_id(request)
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
            extracted_text=extracted_text,
            uploaded_at=datetime.now(timezone.utc),
            is_current=True,
        ))
        session.commit()
    return RedirectResponse(
        f"/resumes?user_id={target_user_id}&message=Document+uploaded;+review+the+suggested+profile+before+saving",
        status_code=303,
    )
