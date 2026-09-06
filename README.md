\
# Calaveras County Job Agent

A two-agent starter system:

1. **Job Scout / ingestion layer** searches configured sources, normalizes jobs,
   enforces Calaveras County locality, verifies timestamp freshness when possible,
   and deduplicates postings.
2. **Resume Evaluator** compares each new local job against a master candidate
   profile derived from the two Joshua George resumes and returns a fit score,
   explanation, gaps, and which resume to use.

## What works now

- SQLite by default; PostgreSQL supported via `DATABASE_URL`.
- Demo provider works without credentials.
- Adzuna provider is implemented and uses its exact `created` timestamp when
  returned.
- 60-minute freshness classification.
- Strict local whitelist filter.
- SHA-256 deduplication fingerprint.
- AI evaluator via OpenAI Responses API when `OPENAI_API_KEY` is present.
- Deterministic fallback evaluator when no OpenAI key is present.
- Resume-selection logic.
- Console alerts.
- Unit tests for locality and freshness.

## Important behavior

A job is **not** considered a verified last-hour job unless an exact timestamp is
available. A job with no timestamp can be stored/evaluated but is not allowed
into the strict immediate-last-hour queue.

The candidate profile also contains truth constraints so the evaluator does not
turn coursework into work experience or claim certifications/skills that the
resumes do not support.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
python run.py
```

The default `JOB_PROVIDER=demo` runs the whole pipeline with a fresh sample
Murphys bookkeeping job.

Run tests:

```bash
python -m unittest discover -s tests -v
```

## Enable AI evaluation

Edit `.env`:

```env
OPENAI_API_KEY=your_key_here
OPENAI_MODEL=gpt-5.6-luna
```

Without an API key, the pipeline still runs but uses a deterministic scoring
prior instead of semantic resume analysis.

## Enable live Adzuna search

1. Register for an Adzuna API application.
2. Add credentials to `.env`:

```env
JOB_PROVIDER=adzuna
ADZUNA_APP_ID=...
ADZUNA_APP_KEY=...
```

3. Run:

```bash
python run.py
```

## PostgreSQL production mode

```env
DATABASE_URL=postgresql+psycopg://jobagent:password@localhost:5432/jobagent
```

Create the database first; SQLAlchemy creates the tables.

## Schedule every 15 minutes

Linux/macOS cron example:

```cron
*/15 * * * * cd /path/to/calaveras_job_agent && .venv/bin/python run.py >> job-agent.log 2>&1
```

For a server deployment, use a service scheduler (systemd timer, container
scheduler, n8n, cloud scheduler) rather than depending on a laptop staying on.

## Processing flow

```text
Scheduler
   |
   v
Provider search
   |
   v
Normalize + local filter + freshness
   |
   v
Deduplicate / persist
   |
   v
Resume Evaluator
   |
   v
Score + resume selection
   |
   +--> verified <=60 min & score >=75 --> immediate alert
   +--> verified <=60 min & score 60-74 --> possible-fit alert
   +--> unverified timestamp & score >=75 --> digest queue
   +--> score <60 --> silent storage
```

## Next production upgrades

- Add an email/SMS notifier.
- Add a second job provider for redundancy.
- Add original-employer-page timestamp verification.
- Add commute-distance calculation from Avery.
- Add a web dashboard for New / Strong Fit / Applied / Rejected.
- Add application tracking and tailored-resume generation after user approval.
