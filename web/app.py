\
from __future__ import annotations

import os
import secrets
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from pathlib import Path

from fastapi import FastAPI, Request, Form, UploadFile, File, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy import select, desc, func

from job_agent.db import init_db, SessionLocal
from job_agent.models import Job, Evaluation, SearchTerm, RunLog, ResumeAsset, ApplicationPackage
from job_agent.application_builder import build_application_materials
from job_agent.source_catalog import get_job_sources
from job_agent.config import load_settings, env
from job_agent.notify import email_notify
from job_agent.settings_store import (
    seed_settings, get_bool, get_int, get_setting, set_setting
)




from .cloud_trigger import trigger_worker
from .resume_storage import save_resume

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
    return bool(request.session.get("authenticated"))

def require_auth(request: Request):
    if not authed(request):
        return RedirectResponse("/login", status_code=303)
    return None

@app.on_event("startup")
def startup():
    init_db()
    with SessionLocal() as session:
        seed_settings(session, load_settings())

@app.get("/health")
def health():
    return {"ok": True}

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse(
        request,
        "login.html",
        {"error": None}
    )

@app.post("/login", response_class=HTMLResponse)
def login(request: Request, password: str = Form(...)):
    configured = env("ADMIN_PASSWORD", "")
    if configured and secrets.compare_digest(password, configured):
        request.session["authenticated"] = True
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(
        request,
        "login.html",
        {"error": "Invalid password."},
        status_code=401
    )

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
        enabled = get_bool(session, "agent_enabled", True)
        latest_run = session.scalar(select(RunLog).order_by(desc(RunLog.started_at)).limit(1))
        total_jobs = session.scalar(select(func.count(Job.id))) or 0
        strong = session.scalar(
            select(func.count(Evaluation.id)).where(Evaluation.fit_score >= 75)
        ) or 0
        recent = session.execute(
            select(Job, Evaluation)
            .join(Evaluation, Evaluation.job_id == Job.id, isouter=True)
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
    denial = require_auth(request)
    if denial:
        return denial
    with SessionLocal() as session:
        current = get_bool(session, "agent_enabled", True)
        set_setting(session, "agent_enabled", "false" if current else "true")
    return RedirectResponse("/", status_code=303)

@app.post("/admin/run-now")
def run_now(request: Request, background_tasks: BackgroundTasks):
    denial = require_auth(request)
    if denial:
        return denial
    background_tasks.add_task(trigger_worker)
    return RedirectResponse("/?message=Run+requested", status_code=303)

@app.post("/admin/test-email")
def test_email(request: Request):
    denial = require_auth(request)
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

    sent, result = email_notify(
        test_job,
        test_evaluation,
        "test",
    )

    if sent:
        return RedirectResponse("/?message=Test+email+sent", status_code=303)

    return RedirectResponse(
        f"/?message=Test+email+failed:+{result}",
        status_code=303,
    )


@app.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request):
    denial = require_auth(request)
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
    schedule_interval_minutes: int = Form(...),
    schedule_start_time: str = Form(...),
    schedule_stop_time: str = Form(...),
    schedule_days: list[str] = Form([]),
    allow_unverified_current_jobs_in_digest: str | None = Form(None),







):
    denial = require_auth(request)
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
    return RedirectResponse("/settings", status_code=303)

@app.post("/settings/search-terms/add")
def add_term(request: Request, term: str = Form(...)):
    denial = require_auth(request)
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
    denial = require_auth(request)
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
    denial = require_auth(request)
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
        stmt = (
            select(Job, Evaluation)
            .join(Evaluation, Evaluation.job_id == Job.id, isouter=True)
            .order_by(*job_sort_order(sort))
        )
        if status:
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
            .where(ApplicationPackage.job_id == job_id)
            .order_by(desc(ApplicationPackage.version))
            .limit(1)
        )

    return templates.TemplateResponse(
        request,
        "application.html",
        {"job": job, "package": package}
    )



@app.post("/jobs/{job_id}/application/build")
def build_application_package(job_id: str, request: Request):
    denial = require_auth(request)
    if denial:
        return denial

    with SessionLocal() as session:
        job = session.get(Job, job_id)
        if not job:
            return HTMLResponse("Job not found", status_code=404)

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
            result = build_application_materials(job_data)
        except Exception:
            return HTMLResponse(
                "Application package generation failed. Please try again.",
                status_code=500,
            )

        current_version = session.scalar(
            select(func.max(ApplicationPackage.version))
            .where(ApplicationPackage.job_id == job_id)
        ) or 0

        now = datetime.now(timezone.utc)
        package = ApplicationPackage(
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


@app.get("/sources", response_class=HTMLResponse)
def sources_page(request: Request):
    denial = require_auth(request)
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
    denial = require_auth(request)
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
def resumes_page(request: Request):
    denial = require_auth(request)
    if denial:
        return denial
    with SessionLocal() as session:
        assets = session.scalars(
            select(ResumeAsset).order_by(desc(ResumeAsset.uploaded_at))
        ).all()
    return templates.TemplateResponse(
        request,
        "resumes.html",
        {"assets": assets}
    )

@app.post("/resumes/upload")
async def upload_resume(
    request: Request,
    resume_type: str = Form(...),
    resume: UploadFile = File(...),
):
    denial = require_auth(request)
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

    uri = save_resume(filename, content, resume_type)
    with SessionLocal() as session:
        previous = session.scalars(
            select(ResumeAsset).where(
                ResumeAsset.resume_type == resume_type,
                ResumeAsset.is_current.is_(True),
            )
        ).all()
        for p in previous:
            p.is_current = False
        session.add(ResumeAsset(
            resume_type=resume_type,
            filename=filename,
            storage_uri=uri,
            uploaded_at=datetime.now(timezone.utc),
            is_current=True,
        ))
        session.commit()
    return RedirectResponse("/resumes", status_code=303)
