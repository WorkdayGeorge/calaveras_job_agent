\
# Google Cloud deployment

This project uses one Docker image in two Cloud Run modes:

- **Cloud Run Service**: `calaveras-job-agent-web` — browser admin dashboard.
- **Cloud Run Job**: `calaveras-job-agent-worker` — Agent 1 + Agent 2 pipeline.
- **Cloud Scheduler**: invokes the worker every 15 minutes.
- **Cloud SQL PostgreSQL**: persistent jobs/settings/run history.
- **Secret Manager**: API keys, DB URL, dashboard password, SMTP credentials.
- **Cloud Storage** (optional but recommended): uploaded resume files.

## Before running commands

Install the Google Cloud CLI and authenticate:

```bash
gcloud auth login
gcloud auth application-default login
gcloud config set project YOUR_PROJECT_ID
```

Choose a region and keep Cloud Run, Cloud SQL, Artifact Registry, and Scheduler together when possible:

```bash
export PROJECT_ID="YOUR_PROJECT_ID"
export REGION="us-west1"
```

## 1. Enable APIs

```bash
gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  cloudscheduler.googleapis.com \
  sqladmin.googleapis.com \
  secretmanager.googleapis.com \
  storage.googleapis.com
```

## 2. Create Artifact Registry

```bash
gcloud artifacts repositories create job-agent \
  --repository-format=docker \
  --location="$REGION"
```

## 3. Build and push

```bash
gcloud builds submit \
  --config cloudbuild.yaml \
  --substitutions=_REGION="$REGION",_REPOSITORY=job-agent,_IMAGE=calaveras-job-agent
```

For a first deployment, you can also use:

```bash
gcloud builds submit --tag "$REGION-docker.pkg.dev/$PROJECT_ID/job-agent/calaveras-job-agent:latest"
```

The remaining examples use the `:latest` tag.

## 4. Create Cloud SQL PostgreSQL

Create a small PostgreSQL instance in the Cloud Console or CLI. Example:

```bash
gcloud sql instances create calaveras-job-agent-db \
  --database-version=POSTGRES_16 \
  --region="$REGION"
```

Then create the database and application user:

```bash
gcloud sql databases create jobagent --instance=calaveras-job-agent-db
gcloud sql users create jobagent_app \
  --instance=calaveras-job-agent-db \
  --password="USE-A-STRONG-RANDOM-PASSWORD"
```

Get the instance connection name:

```bash
gcloud sql instances describe calaveras-job-agent-db \
  --format='value(connectionName)'
```

Your SQLAlchemy URL for Cloud Run will look like:

```text
postgresql+psycopg://jobagent_app:PASSWORD@/jobagent?host=/cloudsql/PROJECT:REGION:INSTANCE
```

URL-encode special characters in the password.

## 5. Create secrets

Create secrets in Secret Manager. At minimum:

- `job-agent-database-url`
- `job-agent-admin-password`
- `job-agent-session-secret`
- `job-agent-openai-key`
- `job-agent-adzuna-id`
- `job-agent-adzuna-key`

Example:

```bash
printf '%s' 'YOUR_VALUE' | gcloud secrets create job-agent-openai-key --data-file=-
```

If a secret already exists, add a new version instead:

```bash
printf '%s' 'NEW_VALUE' | gcloud secrets versions add job-agent-openai-key --data-file=-
```

## 6. Optional resume bucket

```bash
gcloud storage buckets create "gs://$PROJECT_ID-job-agent-resumes" \
  --location="$REGION" \
  --uniform-bucket-level-access
```

## 7. Deploy worker job

Use the Cloud Console for the easiest first deployment because it makes
Secret Manager and Cloud SQL attachment easier to verify visually.

Container command:

```text
python
```

Container arguments:

```text
run.py
```

Set environment variables:

```text
JOB_PROVIDER=adzuna
OPENAI_MODEL=gpt-5.6-luna
APP_ENV=production
```

Map Secret Manager values to:

```text
DATABASE_URL
OPENAI_API_KEY
ADZUNA_APP_ID
ADZUNA_APP_KEY
```

Attach the Cloud SQL instance to the job.

## 8. Deploy dashboard service

Container uses the Dockerfile default command.

Set:

```text
APP_ENV=production
RUN_NOW_MODE=cloud_run_job
GCP_PROJECT_ID=YOUR_PROJECT_ID
GCP_REGION=us-west1
CLOUD_RUN_JOB_NAME=calaveras-job-agent-worker
GCS_BUCKET=YOUR_PROJECT_ID-job-agent-resumes
```

Map secrets:

```text
DATABASE_URL
ADMIN_PASSWORD
SESSION_SECRET
```

Also attach the same Cloud SQL instance.

The dashboard service account needs permission to run the worker job. Grant the
narrowest role that permits `run.jobs.run` in your environment.

For the first MVP, the application has its own password login. Do not reuse a
personal password; store a long random administrator password in Secret Manager.

## 9. Schedule every 15 minutes

Create a service account for Scheduler and grant it permission to execute the
worker job. Then create a Scheduler target for the Cloud Run Jobs Run API, or
use the Cloud Run Job console's "Add Scheduler Trigger" workflow.

Cron expression:

```text
*/15 * * * *
```

Timezone:

```text
America/Los_Angeles
```

The dashboard's **Pause Search** button does not destroy the schedule. The worker
starts, sees `agent_enabled=false` in PostgreSQL, and exits immediately.

## 10. Email

The code supports authenticated SMTP over STARTTLS. Cloud deployments should use
port 587 rather than port 25.

Set:

```text
SMTP_ENABLED=true
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=...
SMTP_PASSWORD=...
ALERT_EMAIL_TO=...
ALERT_EMAIL_FROM=...
```

Store the password in Secret Manager.

## 11. Test order

1. Deploy using `JOB_PROVIDER=demo`.
2. Open the dashboard and sign in.
3. Press **Run Search Now**.
4. Confirm a demo Murphys job appears under Jobs.
5. Check Run History.
6. Pause/Start the agent from the dashboard.
7. Switch the worker to `JOB_PROVIDER=adzuna`.
8. Add Adzuna credentials.
9. Test a live run manually.
10. Create/enable the 15-minute Scheduler trigger.

Do not enable the recurring live schedule until the manual live run succeeds.
