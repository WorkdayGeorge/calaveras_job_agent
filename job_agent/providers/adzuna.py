\
from __future__ import annotations

from datetime import datetime
import time
import requests

from .base import JobProvider
from job_agent.schemas import RawJob
from job_agent.config import env

class AdzunaProvider(JobProvider):
    BASE_URL = "https://api.adzuna.com/v1/api/jobs/us/search/1"

    def __init__(self) -> None:
        self.app_id = env("ADZUNA_APP_ID")
        self.app_key = env("ADZUNA_APP_KEY")
        if not self.app_id or not self.app_key:
            raise RuntimeError("ADZUNA_APP_ID and ADZUNA_APP_KEY are required for JOB_PROVIDER=adzuna")

    def search(self, *, role: str, location: str, results_per_page: int = 25) -> list[RawJob]:
        params = {
            "app_id": self.app_id,
            "app_key": self.app_key,
            "results_per_page": results_per_page,
            "what": role,
            "where": location,
            "sort_by": "date",
            "content-type": "application/json",
        }
        retry_statuses = {429, 500, 502, 503, 504}
        response = None

        for attempt in range(3):
            try:
                response = requests.get(self.BASE_URL, params=params, timeout=30)
            except requests.RequestException:
                if attempt < 2:
                    time.sleep(2 ** attempt)
                    continue
                raise RuntimeError("Adzuna request failed after retries") from None

            if response.status_code in retry_statuses and attempt < 2:
                time.sleep(2 ** attempt)
                continue

            if not response.ok:
                raise RuntimeError(
                    f"Adzuna request failed with HTTP {response.status_code}"
                )

            break

        if response is None:
            raise RuntimeError("Adzuna request failed after retries")

        payload = response.json()

        jobs: list[RawJob] = []
        for item in payload.get("results", []):
            created = item.get("created")
            posted_at = None
            if created:
                # Handles common ISO-8601 timestamps ending in Z.
                posted_at = datetime.fromisoformat(created.replace("Z", "+00:00"))

            company = (item.get("company") or {}).get("display_name") or "Unknown employer"
            loc = (item.get("location") or {}).get("display_name")
            jobs.append(
                RawJob(
                    provider_job_id=str(item.get("id")) if item.get("id") is not None else None,
                    title=item.get("title") or "Untitled role",
                    company=company,
                    location=loc,
                    employment_type=item.get("contract_time") or item.get("contract_type"),
                    description=item.get("description"),
                    posted_at=posted_at,
                    apply_url=item.get("redirect_url") or "",
                    source="adzuna",
                    source_url=item.get("redirect_url"),
                    requirements=[],
                    metadata={"category": (item.get("category") or {}).get("label")},
                )
            )
        return jobs
