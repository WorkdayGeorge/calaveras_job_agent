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
- Optional database-backed administrator and user accounts.
- Email one-time codes, forced first-login password changes, and password reset.

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

## Multi-user authentication rollout

The production-safe default remains the original single-administrator login:

```env
AUTH_MODE=legacy
```

Database-backed accounts, per-user ownership, and administrator-approved
candidate profiles are present. Keep `AUTH_MODE=legacy` during staged rollout
until authorization and production email tests have passed with a test user.

Before enabling database authentication, configure SMTP and set:

```env
AUTH_MODE=database
ADMIN_EMAIL=administrator@example.com
ADMIN_DISPLAY_NAME=Administrator
```

On startup, the service creates the first administrator from `ADMIN_EMAIL` and
the existing `ADMIN_PASSWORD`. The administrator password must contain at least
12 characters. The administrator can then create user accounts under **Users**.
Each user receives an administrator-assigned temporary password, verifies a
six-digit email code at sign-in, and must replace the temporary password before
using the application.

Job postings remain shared and deduplicated. Evaluations, notifications,
resume assets, application packages, and job/application status belong to one
user. Existing legacy records are assigned to the first administrator
idempotently. The Resume Manager lets the administrator select the user whose
resume is being managed. Application Tracking records status, applied date,
follow-up date, interview date, outcome, URL, and private notes.

Each user has a versioned JSON candidate profile under **Users → Profile &
alerts**. New profiles are inactive by default and are never populated by an
automatic resume rewrite. The administrator must review the facts and truth
constraints before activating evaluation. The worker evaluates each active
profile independently, stores only that user's result, and uses that user's
email and immediate/digest preferences. Updating profile facts creates a new
profile version, so older scores and application packages are not presented as
current results. Joshua's existing profile is seeded as `master-profile-v1`,
including the existing Google coursework, QuickBooks, and accounting-experience
truth safeguards.

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

The reusable `usajobs` provider uses the official USAJOBS API. It defaults to
public U.S. Forest Service (`AG11`) openings within 75 miles of Sonora. Configure
`USAJOBS_API_KEY` and `USAJOBS_USER_AGENT` (the email used to request the key)
through environment variables or Secret Manager. Midnight/date-only publication
values remain unverified rather than being treated as exact posting times.

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
