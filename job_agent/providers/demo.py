\
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from .base import JobProvider
from job_agent.schemas import RawJob

class DemoProvider(JobProvider):
    """Produces deterministic local/non-local examples so the whole pipeline runs without API keys."""

    def search(self, *, role: str, location: str, results_per_page: int = 25) -> list[RawJob]:
        now = datetime.now(timezone.utc)
        if "book" in role.lower() or "account" in role.lower() or "admin" in role.lower():
            return [
                RawJob(
                    provider_job_id="demo-local-001",
                    title="Administrative Assistant / Bookkeeper",
                    company="Demo Local Employer",
                    location="Murphys, CA",
                    employment_type="part_time",
                    description=(
                        "Support bookkeeping and office administration. Maintain invoices, "
                        "records and spreadsheets; assist with accounts payable and receivable; "
                        "perform bank reconciliation and general administrative support."
                    ),
                    posted_at=now - timedelta(minutes=28),
                    apply_url="https://example.com/demo-job",
                    source="demo",
                    source_url="https://example.com/demo-job",
                    requirements=[
                        "Microsoft Excel",
                        "Accurate recordkeeping",
                        "Bookkeeping fundamentals",
                        "Accounts payable/receivable familiarity"
                    ],
                )
            ]
        return []
