from __future__ import annotations

from datetime import datetime, timezone
from html.parser import HTMLParser
import html
import json
import re
from typing import Any

import requests

from .base import JobProvider
from .bear_valley import BearValleyProvider
from job_agent.schemas import RawJob


def _clean_html(value: Any) -> str:
    if not value:
        return ""
    text = html.unescape(str(value))
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"</(?:p|li|div|h[1-6])>", "\n", text, flags=re.I)
    text = re.sub(r"<li[^>]*>", "- ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*", "\n", text)
    return text.strip()


def _text_value(value: Any) -> str | None:
    """Normalize API fields that may be either text or a list of text."""
    if isinstance(value, (list, tuple, set)):
        text = ", ".join(str(item).strip() for item in value if str(item).strip())
        return text or None
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _date(value: Any, *formats: str) -> datetime | None:
    if not value:
        return None
    for fmt in formats:
        try:
            return datetime.strptime(str(value), fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _matches(job: RawJob, role: str) -> bool:
    words = {
        word.casefold()
        for word in re.findall(r"[A-Za-z0-9]+", role)
        if len(word) >= 3
    }
    if not words:
        return True
    haystack = " ".join(
        [job.title, job.company, job.description or "", *(job.requirements or [])]
    ).casefold()
    return any(word in haystack for word in words)


class _JsonLdParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.capture = False
        self.buffer: list[str] = []
        self.payloads: list[dict[str, Any]] = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "script" and attributes.get("type") == "application/ld+json":
            self.capture = True
            self.buffer = []

    def handle_endtag(self, tag):
        if tag != "script" or not self.capture:
            return
        self.capture = False
        try:
            payload = json.loads("".join(self.buffer))
        except (TypeError, ValueError):
            return
        if isinstance(payload, dict):
            self.payloads.append(payload)

    def handle_data(self, data):
        if self.capture:
            self.buffer.append(data)


class ResourceConnectionProvider(JobProvider):
    """Official ApplicantPro openings for Calaveras and Amador counties."""

    LIST_URL = "https://trcac.applicantpro.com/core/jobs/7133"
    DETAIL_URL = "https://trcac.applicantpro.com/core/jobs/7133/{job_id}/job-details"
    SOURCE_KEY = "resource_connection"
    GET_PARAMS = {
        "cityUrl": "",
        "countryAbbreviation": "",
        "stateAbbreviation": "",
        "isInternal": 0,
        "showPayFrequency": 1,
        "showLocation": 1,
        "showEmploymentType": 1,
        "showDate": 1,
    }

    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update(
            {"User-Agent": "CalaverasJobAgent/1.0", "Accept": "application/json"}
        )
        self._cached_jobs: list[RawJob] | None = None

    def _detail(self, job_id: str) -> dict[str, Any]:
        response = self.session.get(
            self.DETAIL_URL.format(job_id=job_id), timeout=30
        )
        response.raise_for_status()
        payload = response.json()
        if not payload.get("success") or not isinstance(payload.get("data"), dict):
            return {}
        return payload["data"]

    def _load_jobs(self) -> list[RawJob]:
        response = self.session.get(
            self.LIST_URL,
            params={"getParams": json.dumps(self.GET_PARAMS, separators=(",", ":"))},
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        data = payload.get("data") if payload.get("success") else {}
        items = data.get("jobs", []) if isinstance(data, dict) else []
        jobs: list[RawJob] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            job_id = str(item.get("id") or "").strip()
            title = str(item.get("title") or "").strip()
            apply_url = str(item.get("jobUrl") or "").strip()
            if not job_id or not title or not apply_url:
                continue
            try:
                detail = self._detail(job_id)
            except (requests.RequestException, ValueError):
                detail = {}
            description = _clean_html(
                detail.get("advertisingDescriptionHtml")
                or detail.get("description")
                or item.get("orgTitle")
            )
            minimum = item.get("minSalary")
            maximum = item.get("maxSalary")
            salary = None
            if minimum or maximum:
                salary = " - ".join(
                    f"${value}" for value in (minimum, maximum) if value
                )
                if item.get("payTypeFrame"):
                    salary += f" {item['payTypeFrame']}"
            jobs.append(
                RawJob(
                    provider_job_id=job_id,
                    title=title,
                    company="The Resource Connection",
                    location=str(item.get("jobLocation") or "Calaveras County, CA"),
                    employment_type=_text_value(item.get("employmentType")),
                    description=description,
                    posted_at=_date(
                        detail.get("startDateRef") or item.get("startDateRef"),
                        "%d-%b-%Y",
                        "%b %d, %Y",
                    ),
                    apply_url=apply_url,
                    source=self.SOURCE_KEY,
                    source_url=apply_url,
                    requirements=[],
                    metadata={
                        "department": item.get("orgTitle"),
                        "closing_date": detail.get("endDateRef") or item.get("endDateRef"),
                        "salary": salary,
                        "timestamp_note": (
                            "ApplicantPro supplies a posting date without a time; "
                            "midnight UTC is used."
                        ),
                        "discovered_via": "Mother Lode Job Training",
                    },
                )
            )
        return jobs

    def search(self, *, role: str, location: str, results_per_page: int = 25):
        del location
        if self._cached_jobs is None:
            self._cached_jobs = self._load_jobs()
        return [job for job in self._cached_jobs if _matches(job, role)][
            :results_per_page
        ]


class GoldenSanAndreasProvider(JobProvider):
    """Golden San Andreas Care Center jobs published through Apploi."""

    LIST_URL = "https://apploi.click/golden-san-andreas-care-center-career-page"
    SOURCE_KEY = "golden_san_andreas"
    CARD_PATTERN = re.compile(
        r'<div\s+class="jobs-card"(?P<attrs>.*?)>.*?'
        r'<a\s+class="job-link"\s+href="(?P<url>[^"]+)".*?>(?P<title>.*?)</a',
        re.I | re.S,
    )

    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "CalaverasJobAgent/1.0"})
        self._cached_jobs: list[RawJob] | None = None

    def _job_posting(self, url: str) -> dict[str, Any]:
        response = self.session.get(url, timeout=30)
        response.raise_for_status()
        parser = _JsonLdParser()
        parser.feed(response.text)
        return next(
            (item for item in parser.payloads if item.get("@type") == "JobPosting"),
            {},
        )

    @staticmethod
    def _attribute(attrs: str, name: str) -> str | None:
        match = re.search(rf'{re.escape(name)}="([^"]*)"', attrs, re.I)
        return html.unescape(match.group(1)).strip() if match else None

    def _load_jobs(self) -> list[RawJob]:
        response = self.session.get(self.LIST_URL, timeout=30)
        response.raise_for_status()
        body = html.unescape(response.text)
        jobs: list[RawJob] = []
        seen: set[str] = set()
        for match in self.CARD_PATTERN.finditer(body):
            attrs = match.group("attrs")
            url = html.unescape(match.group("url"))
            title = _clean_html(match.group("title"))
            id_match = re.search(r"/job/(\d+)", url)
            job_id = id_match.group(1) if id_match else ""
            if not job_id or not title or job_id in seen:
                continue
            seen.add(job_id)
            try:
                posting = self._job_posting(url)
            except requests.RequestException:
                posting = {}
            location_data = posting.get("jobLocation", {}).get("address", {})
            location = ", ".join(
                value
                for value in (
                    location_data.get("addressLocality"),
                    location_data.get("addressRegion"),
                )
                if value
            ) or "San Andreas, CA"
            jobs.append(
                RawJob(
                    provider_job_id=job_id,
                    title=str(posting.get("title") or title),
                    company="Golden San Andreas Care Center",
                    location=location,
                    employment_type=_text_value(
                        posting.get("employmentType")
                        or self._attribute(attrs, "data-jobtype")
                    ),
                    description=_clean_html(posting.get("description")),
                    posted_at=_date(posting.get("datePosted"), "%Y-%m-%d"),
                    apply_url=url,
                    source=self.SOURCE_KEY,
                    source_url=url,
                    requirements=[],
                    metadata={
                        "timestamp_note": (
                            "Apploi supplies a posting date without a time; "
                            "midnight UTC is used."
                        ),
                        "discovered_via": "Mother Lode Job Training",
                    },
                )
            )
        return jobs

    def search(self, *, role: str, location: str, results_per_page: int = 25):
        del location
        if self._cached_jobs is None:
            self._cached_jobs = self._load_jobs()
        return [job for job in self._cached_jobs if _matches(job, role)][
            :results_per_page
        ]


class InsightManufacturingProvider(BearValleyProvider):
    CID = "824005bc-0b5e-446f-847a-33863ec245d7"
    COMPANY_NAME = "Insight Manufacturing"
    SOURCE_KEY = "insight_manufacturing"
    DEFAULT_LOCATION = "Murphys, CA"
    LOCAL_LOCATION_TERMS = ("murphys", "calaveras")
    TIMESTAMP_NOTE = (
        "Exact posting timestamp supplied by Insight Manufacturing's public "
        "ADP career-center API."
    )


class CHIPSForestryProvider(JobProvider):
    """Monitor CHIPS' official hiring page without inventing generic openings."""

    PAGE_URL = "https://www.chipsforestry.org/"

    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "CalaverasJobAgent/1.0"})

    def search(self, *, role: str, location: str, results_per_page: int = 25):
        del role, location, results_per_page
        response = self.session.get(self.PAGE_URL, timeout=30)
        response.raise_for_status()
        # CHIPS currently offers a general application rather than discrete jobs.
        return []
