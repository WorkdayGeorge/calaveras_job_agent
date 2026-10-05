from __future__ import annotations

import re

from sqlalchemy import or_, select

from .models import Job


# Keep these labels stable because they are stored on existing job records.
OCCUPATION_CATEGORIES = (
    "Accounting & Bookkeeping",
    "Administrative & Office Support",
    "Customer Service & Sales",
    "Information Technology & Data",
    "Government & Public Service",
    "Healthcare Support",
    "Education & Community Services",
    "Hospitality & Tourism",
    "Operations, Trades & Maintenance",
)
REMOTE_CATEGORY = "Remote Jobs"
JOB_CATEGORY_FILTERS = OCCUPATION_CATEGORIES + (REMOTE_CATEGORY,)
WORK_ARRANGEMENTS = ("onsite", "hybrid", "remote")

_CATEGORY_TERMS = {
    "Accounting & Bookkeeping": (
        "accounting", "accountant", "bookkeeper", "bookkeeping", "accounts payable",
        "accounts receivable", "payroll", "billing", "finance", "financial",
        "tax preparer", "audit",
    ),
    "Administrative & Office Support": (
        "administrative", "administrator", "office assistant", "office coordinator",
        "receptionist", "records clerk", "data entry", "secretary", "executive assistant",
        "office manager", "clerical",
    ),
    "Customer Service & Sales": (
        "customer service", "customer support", "sales", "retail", "cashier",
        "account representative", "call center", "client services", "inside sales",
        "business development",
    ),
    "Information Technology & Data": (
        "information technology", " it ", "software", "developer", "engineer",
        "systems analyst", "technical support", "help desk", "data analyst",
        "database", "integration", "cybersecurity", "network administrator",
        "workday", "peoplesoft",
    ),
    "Government & Public Service": (
        "government", "public service", "county of", "city of", "state of california",
        "federal", "court", "public works", "utility district", "forest service",
        "usda", "usajobs",
    ),
    "Healthcare Support": (
        "healthcare", "health care", "hospital", "medical", "patient access",
        "patient services", "medical records", "clinic", "pharmacy", "dental",
        "care coordinator", "scheduler",
    ),
    "Education & Community Services": (
        "school", "education", "teacher", "instructional", "college", "library",
        "student services", "community services", "social services", "nonprofit",
        "program coordinator",
    ),
    "Hospitality & Tourism": (
        "hotel", "resort", "hospitality", "front desk", "guest services",
        "reservations", "restaurant", "food service", "housekeeping", "tourism",
        "recreation", "casino",
    ),
    "Operations, Trades & Maintenance": (
        "operations", "warehouse", "driver", "delivery", "maintenance", "mechanic",
        "technician", "manufacturing", "construction", "laborer", "custodian",
        "facilities", "installer", "electrician", "plumber", "forestry",
    ),
}

_SOURCE_CATEGORY_HINTS = {
    "calaveras_county": "Government & Public Service",
    "amador_county": "Government & Public Service",
    "tuolumne_county": "Government & Public Service",
    "calcareers": "Government & Public Service",
    "usajobs": "Government & Public Service",
    "calaveras_court": "Government & Public Service",
    "ccwd": "Government & Public Service",
    "amador_water": "Government & Public Service",
    "tuolumne_utilities": "Government & Public Service",
    "edjoin_calaveras": "Education & Community Services",
    "edjoin_amador": "Education & Community Services",
    "edjoin_tuolumne": "Education & Community Services",
    "adventist_health": "Healthcare Support",
    "commonspirit": "Healthcare Support",
    "mact_health": "Healthcare Support",
    "worldmark_angels_camp": "Hospitality & Tourism",
    "bear_valley": "Hospitality & Tourism",
    "greenhorn_creek": "Hospitality & Tourism",
}


def _searchable(*values) -> str:
    return " ".join(str(value or "") for value in values).casefold()


def classify_work_arrangement(
    title: str | None,
    location: str | None,
    description: str | None,
) -> str:
    location_text = _searchable(location)
    combined = _searchable(title, location, description)

    if "hybrid" in combined:
        return "hybrid"
    remote_phrases = (
        "fully remote", "100% remote", "work from home", "work-from-home",
        "telecommute", "telework", "remote position", "remote role",
    )
    if (
        re.search(r"\bremote\b", location_text)
        or any(phrase in combined for phrase in remote_phrases)
    ):
        return "remote"
    return "onsite"


def categorize_job(
    title: str | None,
    company: str | None,
    description: str | None,
    requirements: list[str] | None = None,
    source: str | None = None,
) -> str:
    title_text = f" {_searchable(title)} "
    body_text = f" {_searchable(company, description, ' '.join(requirements or []))} "
    scores = {category: 0 for category in OCCUPATION_CATEGORIES}

    for category, terms in _CATEGORY_TERMS.items():
        for term in terms:
            needle = term.casefold()
            if needle in title_text:
                scores[category] += 4
            if needle in body_text:
                scores[category] += 1

    source_hint = _SOURCE_CATEGORY_HINTS.get(_searchable(source).strip())
    if source_hint:
        scores[source_hint] += 6

    best = max(OCCUPATION_CATEGORIES, key=lambda category: scores[category])
    if scores[best] == 0:
        return "Operations, Trades & Maintenance"
    return best


def classify_job(job: Job) -> tuple[str, str]:
    return (
        categorize_job(
            job.title,
            job.company,
            job.description,
            job.requirements or [],
            job.source,
        ),
        classify_work_arrangement(job.title, job.location, job.description),
    )


def backfill_job_classifications(session) -> int:
    jobs = session.scalars(
        select(Job).where(or_(
            Job.category.is_(None),
            Job.category == "",
            Job.work_arrangement.is_(None),
            Job.work_arrangement == "",
        ))
    ).all()
    for job in jobs:
        category, arrangement = classify_job(job)
        job.category = category
        job.work_arrangement = arrangement
    if jobs:
        session.commit()
    return len(jobs)
