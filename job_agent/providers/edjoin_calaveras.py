from __future__ import annotations

import re
from typing import Any

import requests

from .base import JobProvider, RawJob


class EDJoinCalaverasProvider(JobProvider):
    """EDJOIN jobs for Calaveras County school employers."""

    API_URL = "https://www.edjoin.org/Home/LoadJobsPortalList"

    DISTRICTS = [
        {
            "district_id": 74,
            "name": "Calaveras County Office Of Education",
            "portal": "https://www.edjoin.org/calaverascoe",
        },
        {
            "district_id": 73,
            "name": "Calaveras Unified School District",
            "portal": "https://www.edjoin.org/calaverasusd",
        },
    ]

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent":
                    "Mozilla/5.0 (compatible; CalaverasJobAgent/1.0)",
                "Accept":
                    "application/json, text/javascript, */*; q=0.01",
                "X-Requested-With": "XMLHttpRequest",
            }
        )
        self._jobs = None

    @staticmethod
    def _clean(value: Any) -> str:
        if value is None:
            return ""
        return re.sub(r"\s+", " ", str(value)).strip()

    @staticmethod
    def _microsoft_date_ms(value: Any):
        if not value:
            return None

        match = re.search(r"/Date\((-?\d+)", str(value))
        if not match:
            return None

        try:
            return int(match.group(1))
        except ValueError:
            return None

    def _fetch_district(self, district):
        jobs = []
        page = 1
        total_pages = 1

        while page <= total_pages:
            response = self.session.get(
                self.API_URL,
                params={
                    "rows": 100,
                    "page": page,
                    "catID": 0,
                    "districtID": district["district_id"],
                },
                headers={"Referer": district["portal"]},
                timeout=30,
            )
            response.raise_for_status()

            payload = response.json()

            if page == 1:
                try:
                    total_pages = max(
                        1,
                        int(payload.get("totalPages") or 1),
                    )
                except (TypeError, ValueError):
                    total_pages = 1

            for item in payload.get("data") or []:
                posting_id = item.get("postingID")
                title = self._clean(item.get("positionTitle"))

                if not posting_id or not title:
                    continue

                company = (
                    self._clean(item.get("districtName"))
                    or district["name"]
                )

                city = self._clean(item.get("city"))
                state = (
                    self._clean(item.get("stateName"))
                    or self._clean(item.get("State"))
                    or "CA"
                ).strip()

                if state.lower() in {"california", "ca"}:
                    state = "CA"

                if city:
                    location = (
                        f"{city}, {state} / Calaveras County, CA"
                    )
                else:
                    location = "Calaveras County, CA"

                summary = self._clean(item.get("JobSummary"))
                posting_info = self._clean(
                    item.get("postingInformation")
                )
                salary = self._clean(item.get("salaryInfo"))
                employment_type = self._clean(
                    item.get("FullTimePartTime")
                )

                parts = []

                if summary:
                    parts.append(summary)

                if posting_info and posting_info not in parts:
                    parts.append(posting_info)

                if salary:
                    parts.append(f"Salary: {salary}")

                if employment_type:
                    parts.append(
                        f"Employment type: {employment_type}"
                    )

                description = "\n\n".join(parts)

                apply_url = (
                    "https://www.edjoin.org/Home/JobPosting/"
                    f"{posting_id}"
                )

                creation_date = item.get("CreationDate")

                jobs.append(
                    RawJob(
                        provider_job_id=str(posting_id),
                        title=title,
                        company=company,
                        location=location,
                        employment_type=employment_type or None,
                        description=description,
                        posted_at=None,
                        apply_url=apply_url,
                        source="edjoin_calaveras",
                        source_url=district["portal"],
                        requirements=[],
                        metadata={
                            "district_id": district["district_id"],
                            "district_portal": district["portal"],
                            "creation_date_raw": creation_date,
                            "creation_date_ms":
                                self._microsoft_date_ms(
                                    creation_date
                                ),
                            "posting_date":
                                item.get("postingDate"),
                            "deadline_raw":
                                item.get("displayUntil"),
                            "deadline_type":
                                item.get("displayFlag"),
                            "salary": salary,
                            "job_type":
                                item.get("jobType"),
                            "job_classification":
                                item.get("jobClassification"),
                            "category_name":
                                item.get("categoryName"),
                            "number_openings":
                                item.get("numberOpenings"),
                            "timestamp_note": (
                                "EDJOIN timestamp is not treated "
                                "as verified for strict <=60-minute "
                                "alerts."
                            ),
                        },
                    )
                )

            page += 1

        return jobs

    def _load_jobs(self):
        if self._jobs is not None:
            return self._jobs

        jobs = []

        for district in self.DISTRICTS:
            jobs.extend(self._fetch_district(district))

        unique = {
            job.provider_job_id: job
            for job in jobs
        }

        self._jobs = list(unique.values())
        return self._jobs

    def search(self, role=None, location=None, **kwargs):
        # Return all open Calaveras school jobs.
        # Agent 2 determines candidate fit.
        return self._load_jobs()
