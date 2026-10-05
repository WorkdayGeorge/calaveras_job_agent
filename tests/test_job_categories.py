from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from job_agent.job_categories import (
    JOB_CATEGORY_FILTERS,
    backfill_job_classifications,
    categorize_job,
    classify_work_arrangement,
)
from job_agent.models import Base, Job


def test_category_catalog_has_nine_occupations_plus_remote_view():
    assert len(JOB_CATEGORY_FILTERS) == 10
    assert JOB_CATEGORY_FILTERS[-1] == "Remote Jobs"


def test_job_category_uses_title_and_source_signals():
    assert categorize_job(
        "Accounting Technician",
        "Example Company",
        "Process invoices and reconcile accounts.",
    ) == "Accounting & Bookkeeping"
    assert categorize_job(
        "Office Assistant",
        "Calaveras County",
        "Support a public office.",
        source="calaveras_county",
    ) == "Government & Public Service"
    assert categorize_job(
        "Front Desk Agent",
        "Mountain Resort",
        "Assist hotel guests and reservations.",
    ) == "Hospitality & Tourism"


def test_work_arrangement_is_independent_from_occupation():
    assert classify_work_arrangement(
        "Bookkeeper", "Remote, United States", "Work from home."
    ) == "remote"
    assert classify_work_arrangement(
        "Data Analyst", "Sacramento, CA", "Hybrid schedule with two office days."
    ) == "hybrid"
    assert classify_work_arrangement(
        "Maintenance Technician", "Angels Camp, CA", "On-site facilities role."
    ) == "onsite"


def test_existing_jobs_are_backfilled_once():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    now = datetime.now(timezone.utc)
    job = Job(
        title="Customer Service Representative",
        company="Example Company",
        location="Remote",
        description="Provide customer support from home.",
        apply_url="https://example.com/job",
        source="example",
        first_seen_at=now,
        last_seen_at=now,
        job_fingerprint="c" * 64,
        is_local=True,
        freshness_status="verified_fresh",
    )
    session.add(job)
    session.commit()

    assert backfill_job_classifications(session) == 1
    assert job.category == "Customer Service & Sales"
    assert job.work_arrangement == "remote"
    assert backfill_job_classifications(session) == 0
