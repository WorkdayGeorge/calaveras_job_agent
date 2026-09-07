from __future__ import annotations

import html
import re
import xml.etree.ElementTree as ET

import requests

from .base import JobProvider
from job_agent.schemas import RawJob


class CalaverasCountyProvider(JobProvider):
    FEED_URL = (
        "https://www.governmentjobs.com/"
        "SearchEngine/JobsFeed?agency=calaverascounty"
    )

    NS = {
        "job": "http://www.neogov.com/namespaces/JobListing",
    }

    def __init__(self) -> None:
        self._cached_jobs: list[RawJob] | None = None

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
    def _text(item, name: str) -> str | None:
        element = item.find(name)
        if element is None or element.text is None:
            return None
        return element.text.strip()

    def _job_text(self, item, name: str) -> str | None:
        element = item.find(f"job:{name}", self.NS)
        if element is None or element.text is None:
            return None
        return element.text.strip()

    def _load_feed(self) -> list[RawJob]:
        response = requests.get(
            self.FEED_URL,
            timeout=30,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 "
                    "(compatible; CalaverasJobAgent/1.0)"
                )
            },
        )
        response.raise_for_status()

        root = ET.fromstring(response.content)

        jobs: list[RawJob] = []

        for item in root.findall("./channel/item"):
            title = self._text(item, "title") or "Untitled role"
            link = self._text(item, "link") or ""

            job_id = self._job_text(item, "jobId")
            job_number = self._job_text(item, "jobNumberSingle")

            description = self._clean_html(
                self._text(item, "description")
            )
            duties = self._clean_html(
                self._job_text(item, "examplesofduties")
            )
            qualifications = self._clean_html(
                self._job_text(item, "qualifications")
            )
            supplemental = self._clean_html(
                self._job_text(item, "supplementalinformation")
            )

            combined_description = "\n\n".join(
                part
                for part in [
                    description,
                    duties,
                    qualifications,
                    supplemental,
                ]
                if part
            )

            minimum_salary = self._job_text(item, "minimumSalary")
            maximum_salary = self._job_text(item, "maximumSalary")
            salary_interval = self._job_text(item, "salaryInterval")

            salary = None
            if minimum_salary or maximum_salary:
                salary = (
                    f"{minimum_salary or '?'}-"
                    f"{maximum_salary or '?'}"
                )
                if salary_interval:
                    salary += f" per {salary_interval}"

            source_location = self._job_text(item, "location")

            if source_location:
                location = f"{source_location}, Calaveras County, CA"
            else:
                location = "Calaveras County, CA"

            # Important:
            #
            # NEOGOV provides advertiseFromDateUTC, but the feed shown
            # by Calaveras County normalizes it to midnight. pubDate may
            # reflect a later feed/update event. Neither safely proves
            # the exact original posting time.
            #
            # Therefore posted_at deliberately remains None so this
            # source cannot incorrectly trigger a <=60-minute alert.

            jobs.append(
                RawJob(
                    provider_job_id=job_id or job_number or link,
                    title=title,
                    company="Calaveras County",
                    location=location,
                    employment_type=self._job_text(item, "jobType"),
                    description=combined_description or description,
                    posted_at=None,
                    apply_url=link,
                    source="calaveras_county",
                    source_url=link,
                    requirements=(
                        [qualifications]
                        if qualifications
                        else []
                    ),
                    metadata={
                        "job_number": job_number,
                        "department": self._job_text(
                            item, "department"
                        ),
                        "division": self._job_text(
                            item, "division"
                        ),
                        "advertise_from": self._job_text(
                            item, "advertiseFromDate"
                        ),
                        "advertise_from_utc": self._job_text(
                            item, "advertiseFromDateUTC"
                        ),
                        "closing_date": self._job_text(
                            item, "advertiseToDateTime"
                        ),
                        "salary": salary,
                        "minimum_salary": minimum_salary,
                        "maximum_salary": maximum_salary,
                        "salary_interval": salary_interval,
                        "pub_date": self._text(item, "pubDate"),
                        "timestamp_note": (
                            "NEOGOV advertises an opening date, "
                            "but exact original posting time is "
                            "not verified."
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
            self._cached_jobs = self._load_feed()

        role_words = {
            word.lower()
            for word in re.findall(r"[A-Za-z0-9]+", role)
            if len(word) >= 3
        }

        if not role_words:
            return self._cached_jobs[:results_per_page]

        matches: list[RawJob] = []

        for job in self._cached_jobs:
            haystack = (
                f"{job.title} "
                f"{job.description or ''} "
                f"{' '.join(job.requirements or [])}"
            ).lower()

            if any(word in haystack for word in role_words):
                matches.append(job)

        return matches[:results_per_page]
