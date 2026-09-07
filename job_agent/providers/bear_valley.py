from __future__ import annotations

import html
import re
from datetime import datetime

import requests

from .base import JobProvider
from job_agent.schemas import RawJob


class BearValleyProvider(JobProvider):
    CID = "a9f73c21-b1eb-41af-8b11-4b980fade755"
    CCID = "19000101_000001"

    API_URL = (
        "https://workforcenow.adp.com/mascsr/default/"
        "careercenter/public/events/staffing/v1/job-requisitions"
    )

    APPLY_BASE = (
        "https://workforcenow.adp.com/mascsr/default/mdf/"
        "recruitment/recruitment.html"
    )

    def __init__(self) -> None:
        self._cached_jobs: list[RawJob] | None = None
        self.session = requests.Session()
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 "
                "(compatible; CalaverasJobAgent/1.0)"
            ),
            "Accept": "application/json",
        }

    @staticmethod
    def _clean_html(value: str | None) -> str:
        if not value:
            return ""

        value = html.unescape(value)
        value = re.sub(r"<br\s*/?>", "\n", value, flags=re.I)
        value = re.sub(r"</p>", "\n", value, flags=re.I)
        value = re.sub(r"</li>", "\n", value, flags=re.I)
        value = re.sub(r"<[^>]+>", " ", value)
        value = re.sub(r"[ \t]+", " ", value)
        value = re.sub(r"\n\s*", "\n", value)
        return value.strip()

    @staticmethod
    def _parse_posted_at(value: str | None):
        if not value:
            return None

        try:
            return datetime.fromisoformat(
                value.replace("Z", "+00:00")
            )
        except ValueError:
            return None

    @staticmethod
    def _location_text(job: dict) -> str:
        locations = job.get("requisitionLocations") or []

        for location in locations:
            address = location.get("address") or {}

            city = address.get("cityName")
            state = (
                address.get("countrySubdivisionLevel1") or {}
            ).get("codeValue")

            if city and state:
                return f"{city}, {state}"

            name = (location.get("nameCode") or {}).get(
                "shortName"
            )

            if name:
                return name.strip()

        return "Bear Valley, CA"

    @staticmethod
    def _salary_text(job: dict) -> str | None:
        pay = job.get("payGradeRange") or {}

        minimum = (pay.get("minimumRate") or {}).get(
            "amountValue"
        )
        maximum = (pay.get("maximumRate") or {}).get(
            "amountValue"
        )

        currency = (
            (pay.get("minimumRate") or {}).get("currencyCode")
            or (pay.get("maximumRate") or {}).get("currencyCode")
            or "USD"
        )

        salary_type = None

        custom = job.get("customFieldGroup") or {}

        for field in custom.get("codeFields") or []:
            name = (field.get("nameCode") or {}).get(
                "codeValue"
            )

            if name == "SalaryType":
                salary_type = field.get("shortName")
                break

        if minimum is None and maximum is None:
            return None

        if minimum is not None and maximum is not None:
            text = f"${minimum:g} - ${maximum:g}"
        elif minimum is not None:
            text = f"${minimum:g}"
        else:
            text = f"${maximum:g}"

        if salary_type:
            text += f" {salary_type}"

        if currency != "USD":
            text += f" {currency}"

        return text

    @staticmethod
    def _external_job_id(job: dict) -> str | None:
        custom = job.get("customFieldGroup") or {}

        for field in custom.get("stringFields") or []:
            name = (field.get("nameCode") or {}).get(
                "codeValue"
            )

            if name == "ExternalJobID":
                return field.get("stringValue")

        return None

    def _apply_url(self, job_id: str) -> str:
        return (
            f"{self.APPLY_BASE}"
            f"?cid={self.CID}"
            f"&ccId={self.CCID}"
            f"&lang=en_US"
            f"&jobId={job_id}"
        )

    def _fetch_detail(self, job_id: str) -> dict | None:
        url = f"{self.API_URL}/{job_id}"

        response = self.session.get(
            url,
            params={"cid": self.CID},
            headers=self.headers,
            timeout=30,
        )
        response.raise_for_status()

        data = response.json()

        if not isinstance(data, dict):
            return None

        return data

    def _fetch_page(self, skip: int) -> tuple[list[dict], int]:
        response = self.session.get(
            self.API_URL,
            params={
                "cid": self.CID,
                "$skip": skip,
                "$top": 20,
            },
            headers=self.headers,
            timeout=30,
        )
        response.raise_for_status()

        data = response.json()

        jobs = data.get("jobRequisitions") or []
        total = (data.get("meta") or {}).get(
            "totalNumber"
        ) or 0

        return jobs, int(total)

    def _load_jobs(self) -> list[RawJob]:
        summaries: list[dict] = []
        seen_ids: set[str] = set()

        # ADP's public career center behaves as a
        # one-based paginated result set.
        skip = 1
        total = None

        while True:
            page, page_total = self._fetch_page(skip)

            if total is None:
                total = page_total

            if not page:
                break

            for item in page:
                job_id = str(item.get("itemID") or "")

                if not job_id or job_id in seen_ids:
                    continue

                seen_ids.add(job_id)
                summaries.append(item)

            if total and len(seen_ids) >= total:
                break

            skip += 20

            # Safety guard against an unexpected API behavior.
            if skip > 1001:
                break

        jobs: list[RawJob] = []

        for summary in summaries:
            job_id = str(summary.get("itemID") or "")

            try:
                detail = self._fetch_detail(job_id)
            except (
                requests.RequestException,
                ValueError,
            ):
                detail = None

            job = detail or summary

            title = (
                job.get("requisitionTitle")
                or summary.get("requisitionTitle")
                or "Untitled role"
            )

            location = self._location_text(job)

            # Keep this source strictly local.
            location_low = location.lower()

            if (
                "bear valley" not in location_low
                and "calaveras" not in location_low
            ):
                continue

            description = self._clean_html(
                job.get("requisitionDescription")
            )

            posted_raw = (
                job.get("postDate")
                or summary.get("postDate")
            )

            posted_at = self._parse_posted_at(
                posted_raw
            )

            work_level = (
                job.get("workLevelCode") or {}
            ).get("shortName")

            salary = self._salary_text(job)

            external_job_id = self._external_job_id(job)

            apply_url = self._apply_url(job_id)

            jobs.append(
                RawJob(
                    provider_job_id=job_id,
                    title=title,
                    company="Bear Valley Mountain Resort",
                    location=location,
                    employment_type=work_level,
                    description=description,
                    posted_at=posted_at,
                    apply_url=apply_url,
                    source="bear_valley",
                    source_url=apply_url,
                    requirements=[],
                    metadata={
                        "client_requisition_id": (
                            job.get("clientRequisitionID")
                        ),
                        "external_job_id": external_job_id,
                        "salary": salary,
                        "adp_post_date": posted_raw,
                        "timestamp_note": (
                            "Exact posting timestamp supplied "
                            "by Bear Valley's public ADP "
                            "career-center API."
                        ),
                    },
                )
            )

        return jobs

    def search(
        self,
        *,
        role: str,
        location: str,
        results_per_page: int = 25,
    ) -> list[RawJob]:

        if self._cached_jobs is None:
            self._cached_jobs = self._load_jobs()

        role_words = {
            word.lower()
            for word in re.findall(
                r"[A-Za-z0-9]+",
                role,
            )
            if len(word) >= 3
        }

        if not role_words:
            return self._cached_jobs[:results_per_page]

        matches: list[RawJob] = []

        for job in self._cached_jobs:
            haystack = (
                f"{job.title} "
                f"{job.company} "
                f"{job.description or ''}"
            ).lower()

            if any(word in haystack for word in role_words):
                matches.append(job)

        return matches[:results_per_page]
