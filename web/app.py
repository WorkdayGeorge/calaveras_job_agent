\
from __future__ import annotations

import os
import secrets
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Request, Form, UploadFile, File, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy import select, desc, func

from job_agent.db import init_db, SessionLocal
from job_agent.models import Job, Evaluation, SearchTerm, RunLog, ResumeAsset
from job_agent.config import load_settings, env
from job_agent.settings_store import (
    seed_settings, get_bool, get_int, set_setting
)
from .cloud_trigger import trigger_worker
from .resume_storage import save_resume

BASE_DIR = Path(__file__).resolve().parents[1]
templates = Jinja2Templates(directory=str(BASE_DIR / "web" / "templates"))

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
    return templates.TemplateResponse("login.html", {"request": request, "error": None})

@app.post("/login", response_class=HTMLResponse)
def login(request: Request, password: str = Form(...)):
    configured = env("ADMIN_PASSWORD", "")
    if configured and secrets.compare_digest(password, configured):
        request.session["authenticated"] = True
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(
        "login.html", {"request": request, "error": "Invalid password."}, status_code=401
    )

@app.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)

@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
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
            .order_by(desc(Job.first_seen_at))
            .limit(8)
        ).all()

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "enabled": enabled,
        "latest_run": latest_run,
        "total_jobs": total_jobs,
        "strong": strong,
        "recent": recent,
    })

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
        }
    return templates.TemplateResponse(
        "settings.html", {"request": request, "terms": terms, "values": values}
    )

@app.post("/settings")
def save_settings(
    request: Request,
    fresh_job_window_minutes: int = Form(...),
    minimum_fit_score: int = Form(...),
    immediate_alert_score: int = Form(...),
    allow_unverified_current_jobs_in_digest: str | None = Form(None),
):
    denial = require_auth(request)
    if denial:
        return denial
    with SessionLocal() as session:
        set_setting(session, "fresh_job_window_minutes", str(max(1, fresh_job_window_minutes)))
        set_setting(session, "minimum_fit_score", str(max(0, min(100, minimum_fit_score))))
        set_setting(session, "immediate_alert_score", str(max(0, min(100, immediate_alert_score))))
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
def jobs_page(request: Request, status: str | None = None):
    denial = require_auth(request)
    if denial:
        return denial
    with SessionLocal() as session:
        stmt = (
            select(Job, Evaluation)
            .join(Evaluation, Evaluation.job_id == Job.id, isouter=True)
            .order_by(desc(Job.first_seen_at))
        )
        if status:
            stmt = stmt.where(Job.status == status)
        rows = session.execute(stmt.limit(250)).all()
    return templates.TemplateResponse(
        "jobs.html", {"request": request, "rows": rows, "status_filter": status}
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

@app.get("/runs", response_class=HTMLResponse)
def runs_page(request: Request):
    denial = require_auth(request)
    if denial:
        return denial
    with SessionLocal() as session:
        runs = session.scalars(select(RunLog).order_by(desc(RunLog.started_at)).limit(100)).all()
    return templates.TemplateResponse("runs.html", {"request": request, "runs": runs})

@app.get("/resumes", response_class=HTMLResponse)
def resumes_page(request: Request):
    denial = require_auth(request)
    if denial:
        return denial
    with SessionLocal() as session:
        assets = session.scalars(
            select(ResumeAsset).order_by(desc(ResumeAsset.uploaded_at))
        ).all()
    return templates.TemplateResponse("resumes.html", {"request": request, "assets": assets})

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
