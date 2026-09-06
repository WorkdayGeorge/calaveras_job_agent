\
# Calaveras County Job Agent — Version 2

A deployable job-search and resume-fit system for Joshua George.

## What Version 2 adds

- Browser-based administration dashboard.
- Password-protected admin login.
- **Start / Pause Search** control.
- **Run Search Now** control.
- Editable search terms.
- Editable freshness / fit / alert thresholds.
- PostgreSQL-backed application settings.
- Job review and application statuses.
- Run history and error logging.
- SMTP email alerts.
- Resume-version upload/storage tracking.
- Docker container.
- Cloud Run Service + Cloud Run Job architecture.
- Google Cloud deployment guide.
- GitHub Actions unit tests.

The original two-agent engine remains:

1. **Scout** finds and normalizes jobs and enforces locality/timestamp rules.
2. **Evaluator** compares new jobs with Joshua's master candidate profile.

## Local test

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` and set at least:

```env
ADMIN_PASSWORD=choose-a-long-password
SESSION_SECRET=choose-a-different-long-random-secret
JOB_PROVIDER=demo
```

Start the dashboard:

```bash
uvicorn web.app:app --reload
```

Open:

```text
http://127.0.0.1:8000
```

The demo provider does not require API credentials.

## Worker only

```bash
python run.py
```

## Docker

```bash
docker build -t calaveras-job-agent .
docker run --rm -p 8080:8080 --env-file .env calaveras-job-agent
```

Then open:

```text
http://localhost:8080
```

## Live job provider

Set:

```env
JOB_PROVIDER=adzuna
ADZUNA_APP_ID=...
ADZUNA_APP_KEY=...
```

Adzuna's returned `created` timestamp is used when available. Jobs without an
exact timestamp are never promoted to the strict "verified within 60 minutes"
queue.

## OpenAI evaluator

Set:

```env
OPENAI_API_KEY=...
OPENAI_MODEL=gpt-5.6-luna
```

If no OpenAI key is present, the system still runs using the deterministic
fallback evaluator.

## Job statuses

The dashboard supports:

```text
new
reviewed
interested
applied
interview
rejected
hired
ignore
expired
```

## Resume uploads

The Resume Manager can store current focused and all-work-experience DOCX/PDF
files. Configure `GCS_BUCKET` in Google Cloud for persistent storage.

For safety, Version 2 does **not** automatically rewrite the master candidate
profile from an uploaded resume. This prevents a parsing/model error from
silently adding qualifications Joshua does not have.

## Google Cloud

See:

```text
deploy/gcp/README.md
```

Recommended production architecture:

```text
Cloud Run Service
    Admin dashboard
          |
          v
Cloud SQL PostgreSQL
          ^
          |
Cloud Run Job <--- Cloud Scheduler (every 15 minutes)
          |
          +--- Secret Manager
          +--- OpenAI
          +--- Job provider
          +--- SMTP email
```

## Security notes

- Never commit `.env`.
- Put API keys/passwords in Google Secret Manager.
- Use a long random `ADMIN_PASSWORD` and separate `SESSION_SECRET`.
- Use HTTPS in production (Cloud Run provides HTTPS).
- Do not make the database public to the internet unless you have a specific
  reason and understand the network controls.
- The agent does not auto-apply to jobs.
