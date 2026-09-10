from __future__ import annotations

from .config import env

JOB_SOURCES = [
    {
        "key": "adzuna",
        "name": "Adzuna",
        "type": "Job aggregator",
        "description": "Broad job search source used to find additional local openings.",
        "links": [
            {"label": "Adzuna", "url": "https://www.adzuna.com/"}
        ],
    },
    {
        "key": "calaveras_county",
        "name": "Calaveras County Government Jobs",
        "type": "Local government",
        "description": "Official Calaveras County job postings hosted by GovernmentJobs/NEOGOV.",
        "links": [
            {"label": "GovernmentJobs", "url": "https://www.governmentjobs.com/"}
        ],
    },
    {
        "key": "calcareers",
        "name": "CalCareers",
        "type": "State government",
        "description": "California state job openings through the official CalCareers site.",
        "links": [
            {"label": "CalCareers", "url": "https://calcareers.ca.gov/"}
        ],
    },
    {
        "key": "commonspirit",
        "name": "CommonSpirit Health / Mark Twain Medical Center",
        "type": "Healthcare",
        "description": "CommonSpirit Health careers, including local healthcare openings.",
        "links": [
            {"label": "CommonSpirit Careers", "url": "https://www.commonspirit.careers/"}
        ],
    },
    {
        "key": "bear_valley",
        "name": "Bear Valley Mountain Resort",
        "type": "Local employer",
        "description": "Bear Valley Mountain Resort career openings hosted through ADP Workforce Now.",
        "links": [
            {"label": "Bear Valley Careers", "url": "https://workforcenow.adp.com/mascsr/default/"}
        ],
    },
    {
        "key": "ccwd",
        "name": "Calaveras County Water District",
        "type": "Local public agency",
        "description": "Official CCWD job opportunities.",
        "links": [
            {"label": "CCWD Job Opportunities", "url": "https://www.ccwd.org/job-opportunities"}
        ],
    },
    {
        "key": "edjoin_calaveras",
        "name": "EDJOIN - Calaveras Schools",
        "type": "Education",
        "description": "Public school jobs from Calaveras County Office of Education and Calaveras Unified School District.",
        "links": [
            {"label": "Calaveras County Office of Education", "url": "https://www.edjoin.org/calaverascoe"},
            {"label": "Calaveras Unified School District", "url": "https://www.edjoin.org/calaverasusd"}
        ],
    },
]


def get_job_sources() -> list[dict]:
    raw = env("JOB_PROVIDERS") or env("JOB_PROVIDER", "demo") or "demo"
    enabled = {name.strip().lower() for name in raw.split(",") if name.strip()}

    result = []
    for source in JOB_SOURCES:
        item = dict(source)
        item["enabled"] = item["key"] in enabled
        result.append(item)
    return result
